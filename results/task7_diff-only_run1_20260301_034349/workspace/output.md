# Technical Design Document: KVStorm Distributed Key-Value Store

**Author:** Sarah Chen, Principal Engineer
**Date:** February 10, 2026
**Status:** Under Review
**Version:** 2.0
**Reviewers:** James Alvaro, Priya Nair, Tom Richter, Diana Kowalski

---

## 1. Executive Summary

This document describes the technical design for KVStorm, a distributed key-value store optimised for low-latency reads and high write throughput. KVStorm is intended to replace our ageing Redis cluster infrastructure, which has reached its scalability limits at approximately 2.4 million operations per second. The new system targets 10 million ops/sec with 99th percentile latency under 5 milliseconds.

KVStorm will serve as the primary data store for our real-time recommendation engine, session management layer, feature flag service, and the newly proposed A/B testing platform. The system must support our current dataset of approximately 4.8 TB with room to grow to 50 TB over the next three years.

This design has been informed by our experience operating distributed systems at scale, as well as the academic literature on distributed consensus and eventual consistency models. We draw particular inspiration from Amazon's Dynamo paper, Google's Bigtable, and Meta's RocksDB.

## 2. System Architecture

### 2.1 High-Level Overview

KVStorm employs a shared-nothing architecture where each node is responsible for a subset of the keyspace. The system is organised into a ring topology using consistent hashing with virtual nodes. Each physical node hosts between 128 and 512 virtual nodes depending on its hardware capabilities.

The system consists of four main components:

1. **Storage Engine** - A custom LSM-tree based engine built on top of RocksDB
2. **Coordination Layer** - Handles cluster membership, failure detection, and rebalancing
3. **Client Library** - Provides a simple API for applications to interact with the store
4. **Monitoring Daemon** - Collects metrics and reports cluster health

The architecture prioritises availability and partition tolerance, placing it firmly in the AP category of the CAP theorem. However, we provide tunable consistency levels that allow operators to make different trade-offs on a per-request basis.

### 2.2 Node Architecture

Each KVStorm node runs as a single process with multiple threads. The internal architecture of a node is as follows:

```
+---------------------+
|    Network Layer     |
|   (TCP + gRPC)      |
+---------------------+
|   Request Router     |
+---------------------+
|   Query Processor    |
+---------------------+
|   Storage Engine     |
|   (LSM-Tree)        |
+---------------------+
|   Replication Mgr    |
+---------------------+
|   Gossip Protocol    |
+---------------------+
```

The network layer handles incoming client connections and inter-node communication. We use gRPC for all communication, with Protocol Buffers for serialisation. Each node maintains a connection pool to every other node in the cluster, with a maximum of 64 connections per peer.

### 2.3 Data Partitioning

Data is partitioned across nodes using consistent hashing with the xxHash algorithm. Each key is hashed to a 128-bit value, which is then mapped to a position on the hash ring. The node responsible for a key is the first node encountered when walking clockwise around the ring from the key's position.

To ensure even data distribution, each physical node is assigned multiple virtual nodes. The number of virtual nodes per physical node is proportional to the node's storage capacity and CPU resources. This approach allows us to add heterogeneous hardware to the cluster without creating hotspots.

When a node joins or leaves the cluster, only the keys that map to the affected virtual nodes need to be redistributed. This minimises data movement during cluster membership changes.

### 2.4 Memory Management

KVStorm uses a tiered memory architecture:

- **L1 Cache**: A lock-free concurrent hash map stored in each node's memory, holding the most frequently accessed keys. Maximum size is configurable but defaults to 4 GB per node.
- **L2 Cache**: A shared memory segment that multiple nodes on the same physical machine can access. This is used for cross-partition queries.
- **L3 Storage**: The on-disk LSM-tree managed by RocksDB. This is the durable persistence layer.

The L1 cache uses a W-TinyLFU eviction policy, which provides superior hit rates compared to LRU for real-world access patterns. Cache entries are invalidated using a publish-subscribe mechanism when a key is updated on any node.

## 3. Consistency Model

### 3.1 Overview

KVStorm supports multiple consistency levels that can be specified on a per-operation basis. The available levels are:

| Level | Description | Use Case |
|-------|-------------|----------|
| `ONE` | Write/read acknowledged by a single node | Highest performance, lowest consistency |
| `QUORUM` | Write/read acknowledged by a majority of replicas | Good balance of performance and consistency |
| `ALL` | Write/read acknowledged by all replicas | Strongest consistency, lowest availability |
| `LOCAL_QUORUM` | Quorum within the local data centre | Multi-data-centre deployments |
| `LEADER` | Read/write through the partition leader | Linearizable consistency |

The default consistency level is `QUORUM`, which provides strong consistency under the assumption that clients always read from and write to overlapping quorum sets (i.e., R + W > N).

### 3.2 Hybrid Logical Clocks

To track causality between updates, KVStorm uses Hybrid Logical Clocks (HLCs). HLCs combine a physical timestamp component with a logical counter, providing the causal ordering guarantees of vector clocks without the O(n) space overhead per entry. Each node maintains an HLC that is updated on every write operation.

When conflicting versions are detected during a read, the system can either:

1. Return all conflicting versions to the client for application-level resolution
2. Automatically resolve using last-write-wins based on HLC timestamps
3. Use a custom conflict resolution function registered by the application

HLCs are bounded in size and do not require pruning, eliminating the false conflict issue inherent in pruned vector clocks.

### 3.3 Anti-Entropy Protocol

KVStorm runs a background anti-entropy process based on Merkle trees. Each node maintains a Merkle tree over its portion of the keyspace, and periodically exchanges tree roots with its replica peers. When differences are detected, the affected key ranges are synchronised.

The anti-entropy process runs every 10 minutes by default. Each synchronisation cycle processes at most 5000 keys to limit the impact on foreground operations. These parameters are configurable via the admin API.

### 3.4 Read Repair

When a read operation detects that replicas have divergent values for a key, the system initiates a read repair process. The most recent value (as determined by the HLC timestamp) is written back to all out-of-date replicas. Read repair runs asynchronously in a background thread pool and does not block the client read.

Read repair can be disabled on a per-namespace basis for workloads where stale reads are acceptable and the overhead of repair is undesirable.

## 4. Replication Strategy

### 4.1 Replication Factor

KVStorm uses a configurable replication factor, denoted as N. The default value is N=3, meaning each key is stored on three distinct physical nodes. The replication factor can be configured at the namespace level, allowing different datasets to have different durability guarantees. We recommend N=5 for mission-critical data.

### 4.2 Replica Placement

Replicas are placed on consecutive nodes along the hash ring, skipping virtual nodes that map to the same physical node or the same failure domain (rack). In multi-data-centre deployments, replicas are distributed such that at least one copy exists in each data centre.

The replica placement algorithm is as follows:

```python
def select_replicas(key, ring, replication_factor, topology):
    hash_value = xxhash_128(key)
    position = find_position(ring, hash_value)
    replicas = []
    seen_nodes = set()
    seen_racks = set()

    while len(replicas) < replication_factor:
        node = ring[position]
        rack = topology.get_rack(node.physical_id)
        if node.physical_id not in seen_nodes and rack not in seen_racks:
            replicas.append(node)
            seen_nodes.add(node.physical_id)
            seen_racks.add(rack)
        position = (position + 1) % len(ring)

    # Fallback: if not enough unique racks, relax rack constraint
    if len(replicas) < replication_factor:
        position = find_position(ring, hash_value)
        while len(replicas) < replication_factor:
            node = ring[position]
            if node.physical_id not in seen_nodes:
                replicas.append(node)
                seen_nodes.add(node.physical_id)
            position = (position + 1) % len(ring)

    return replicas
```

### 4.3 Write Path

When a client issues a write request, it is routed to any node in the cluster (the coordinator). The coordinator determines the replica set for the key and forwards the write to all replicas simultaneously. The write is considered successful when the required number of acknowledgements (determined by the consistency level) is received.

The write path consists of the following steps:

1. Client sends write request to coordinator
2. Coordinator computes hash and determines replica set
3. Coordinator validates the request (key size, value size, TTL range)
4. Coordinator forwards write to all N replicas in parallel
5. Each replica writes to its commit log (WAL) and memtable
6. Each replica sends acknowledgement to coordinator
7. Coordinator responds to client after receiving W acknowledgements
8. Any remaining acknowledgements are processed asynchronously

If a replica is unavailable during a write, the coordinator stores a "hinted handoff" -- the write is saved locally and forwarded to the target replica when it becomes available again.

### 4.4 Read Path

The read path mirrors the write path. The coordinator sends read requests to all N replicas and waits for R responses. If the responses are consistent, the value is returned immediately. If they diverge, conflict resolution is performed as described in Section 3.2.

```python
def handle_read(key, consistency_level):
    replicas = select_replicas(key, ring, N, topology)
    R = get_required_responses(consistency_level)

    futures = send_parallel_reads(replicas)
    received = wait_for_responses(futures, count=R, timeout_ms=500)

    if len(received) < R:
        raise InsufficientReplicasError(
            f"Only {len(received)}/{R} replicas responded for key '{key}'"
        )

    if all_consistent(received):
        return received[0].value
    else:
        resolved = resolve_conflict(received)
        schedule_read_repair(key, resolved, replicas)
        return resolved.value
```

## 5. Failure Handling

### 5.1 Failure Detection

KVStorm uses a gossip-based failure detection protocol inspired by the Phi Accrual Failure Detector. Each node periodically sends heartbeat messages to a random subset of peers (fanout of 3). The failure detector maintains a sliding window of inter-arrival times for heartbeats from each peer and computes a "suspicion level" (phi value).

A node is considered suspect when its phi value exceeds 6.0, and confirmed failed when it exceeds 10.0. This two-threshold approach reduces false positives while maintaining fast detection times. The failure detector adapts to varying network conditions automatically.

The gossip protocol disseminates membership changes through the cluster. When a node detects a failure, it broadcasts this information, and the cluster converges on a consistent view of membership within O(log N) gossip rounds, where N is the cluster size.

### 5.2 Hinted Handoff

When a write is destined for an unavailable node, the coordinator stores the write as a "hint" in a local persistent queue. The hint contains:

- The target node identifier
- The key and value to be written
- The HLC timestamp for the write
- A creation timestamp for hint expiry
- The original consistency level requested

Hints are periodically checked (every 10 seconds) and forwarded to the target node when it becomes available. Hints older than 6 hours are discarded under the assumption that the anti-entropy protocol will repair the inconsistency. The hint store is bounded to 1 GB per node to prevent unbounded disk usage.

### 5.3 Split Brain Handling

In the event of a network partition, KVStorm continues to accept reads and writes on both sides of the partition (AP behaviour). When the partition heals, conflicting writes are reconciled using the conflict resolution strategy configured for each namespace.

To detect and recover from split-brain scenarios, each node maintains a partition epoch counter that is incremented whenever a membership change is detected. During partition healing, nodes exchange epoch counters and reconcile their views of the cluster state.

### 5.4 Permanent Failure Recovery

When a node is permanently lost (hardware failure, disk corruption), the cluster initiates a recovery process:

1. An operator confirms the node is permanently failed via the admin API
2. The failed node's virtual nodes are reassigned to other physical nodes
3. Data is reconstructed from surviving replicas using streaming transfers
4. Merkle tree synchronisation ensures completeness and correctness
5. The recovered virtual nodes begin serving traffic after verification

Full recovery of a 500 GB node typically takes between 1-2 hours, depending on network bandwidth and foreground load. Recovery speed has been improved since v1 by implementing parallel streaming from multiple source replicas.

## 6. API Design

### 6.1 Core Operations

KVStorm exposes a key-value API with the following core operations:

```protobuf
service KVStorm {
    rpc Get(GetRequest) returns (GetResponse);
    rpc Put(PutRequest) returns (PutResponse);
    rpc Delete(DeleteRequest) returns (DeleteResponse);
    rpc BatchGet(BatchGetRequest) returns (BatchGetResponse);
    rpc BatchPut(BatchPutRequest) returns (BatchPutResponse);
    rpc Scan(ScanRequest) returns (stream ScanResponse);
    rpc Watch(WatchRequest) returns (stream WatchEvent);
}

message GetRequest {
    string key = 1;
    ConsistencyLevel consistency = 2;
    int64 timeout_ms = 3;
    bool allow_stale = 4;
}

message GetResponse {
    bytes value = 1;
    HybridLogicalClock version = 2;
    bool found = 3;
    NodeInfo served_by = 4;
}

message PutRequest {
    string key = 1;
    bytes value = 2;
    ConsistencyLevel consistency = 3;
    int64 ttl_seconds = 4;
    HybridLogicalClock expected_version = 5;
    map<string, string> metadata = 6;
}

message PutResponse {
    HybridLogicalClock version = 1;
    bool success = 2;
    string error_detail = 3;
}
```

### 6.2 Key and Value Constraints

- Keys must be UTF-8 encoded strings with a maximum length of 512 bytes
- Values can be arbitrary byte sequences with a maximum size of 4 MB
- Keys cannot contain null bytes or the reserved prefix `__kvstorm_`
- Namespaces are specified as key prefixes separated by a forward slash (e.g., `sessions/user123`)

### 6.3 TTL Support

Keys can be assigned a time-to-live (TTL) value at write time. Expired keys are lazily removed during reads and proactively removed during compaction. The TTL resolution is 1 second, and the maximum TTL is 30 days.

TTL is implemented using a separate expiration index stored as a sorted set keyed by expiration timestamp, enabling efficient bulk deletion of expired keys during background sweeps that run every 60 seconds.

### 6.4 Conditional Writes

KVStorm supports compare-and-swap (CAS) operations through the `expected_version` field in the PutRequest. If the current version of the key does not match the expected version, the write is rejected with a `VERSION_MISMATCH` error. This enables optimistic concurrency control without explicit locking.

Additionally, KVStorm supports conditional writes with arbitrary predicates through a lightweight transaction API (see Section 6.6).

### 6.5 Client Library

The client library is available for Java, Python, Go, Rust, and C++. It handles:

- Connection pooling and load balancing across nodes
- Automatic retry with exponential backoff and jitter
- Topology-aware request routing based on key hash
- Circuit breaking for unresponsive nodes
- Client-side metrics collection and reporting
- Automatic serialisation/deserialisation for common types

Example usage in Go:

```go
package main

import (
    "context"
    "fmt"
    "log"
    "time"

    kvstorm "github.com/kvstorm/client-go/v2"
)

func main() {
    client, err := kvstorm.NewClient(kvstorm.Config{
        Seeds:            []string{"node1:9090", "node2:9090", "node3:9090"},
        Consistency:      kvstorm.Quorum,
        DefaultTimeout:   500 * time.Millisecond,
        MaxRetries:       3,
        CircuitBreaker:   kvstorm.DefaultCircuitBreaker(),
    })
    if err != nil {
        log.Fatalf("failed to create client: %v", err)
    }
    defer client.Close()

    ctx := context.Background()

    // Write a value with TTL
    err = client.Put(ctx, "user:123", []byte("john"), kvstorm.WithTTL(1*time.Hour))
    if err != nil {
        log.Fatalf("put failed: %v", err)
    }

    // Read a value
    result, err := client.Get(ctx, "user:123")
    if err != nil {
        log.Fatalf("get failed: %v", err)
    }
    if result.Found {
        fmt.Printf("Value: %s (version: %v)\n", result.Value, result.Version)
    }
}
```

## 7. Performance Benchmarks

### 7.1 Test Environment

All benchmarks were conducted on a cluster of 12 nodes, each with:

- 32-core AMD EPYC 7543 processor
- 256 GB DDR4 RAM
- 4x Samsung 990 Pro NVMe SSD (2 TB each)
- 25 Gbps network interconnect (dual-homed)

The test dataset consisted of 2 billion key-value pairs with an average key size of 48 bytes and an average value size of 256 bytes. Benchmarks used a Zipfian distribution with theta=0.99 to simulate realistic access patterns.

### 7.2 Throughput Results

| Operation | Consistency | Throughput (ops/sec) | p50 Latency | p99 Latency | p99.9 Latency |
|-----------|-------------|---------------------|-------------|-------------|---------------|
| GET | ONE | 14,200,000 | 0.2 ms | 0.9 ms | 2.1 ms |
| GET | QUORUM | 9,100,000 | 0.6 ms | 2.4 ms | 5.8 ms |
| GET | ALL | 4,800,000 | 1.2 ms | 5.1 ms | 11.2 ms |
| PUT | ONE | 7,600,000 | 0.4 ms | 1.8 ms | 3.9 ms |
| PUT | QUORUM | 5,200,000 | 0.9 ms | 3.8 ms | 8.4 ms |
| PUT | ALL | 2,800,000 | 1.9 ms | 7.6 ms | 15.3 ms |
| BatchGET (100) | QUORUM | 850,000 | 2.1 ms | 8.4 ms | 18.7 ms |

These results demonstrate that KVStorm exceeds its target of 10 million ops/sec for the most common workload (GET with QUORUM consistency).

### 7.3 Scalability

Linear scalability was observed up to 64 nodes. Beyond this point, the gossip protocol overhead begins to impact performance. We plan to implement a hierarchical gossip protocol with swim-style protocol extensions to push this limit to 500+ nodes.

Scaling characteristics:

- Adding a node increases total cluster throughput by approximately 750,000 ops/sec
- Rebalancing after node addition completes within 20 minutes for a 4 TB dataset
- Less than 5% impact on foreground operations during rebalancing (with rate limiting enabled)

### 7.4 Failure Scenarios

We tested various failure scenarios to ensure the system maintains performance under adverse conditions:

- **Single node failure**: Less than 2% throughput drop, client failover within 5 seconds
- **Data centre failure**: 45% throughput drop (expected with 2 data centres), recovery within 30 seconds
- **Network partition**: Each partition continues to serve requests at reduced throughput
- **Disk failure**: Affected node evacuates data to peers within 10 minutes
- **Cascading failure (3 nodes)**: 15% throughput drop with N=5 replication, automatic recovery

## 8. Deployment Considerations

### 8.1 Hardware Requirements

Minimum hardware requirements per node:

- 16 CPU cores (32 recommended)
- 64 GB RAM (128 GB recommended)
- 1 TB NVMe SSD storage (2 TB recommended)
- 10 Gbps network interface (25 Gbps recommended)

For optimal performance, we recommend dedicated bare-metal machines. The storage engine relies heavily on direct I/O and memory-mapped files, which perform poorly in virtualised environments. Containerised deployments are supported but require privileged I/O access.

### 8.2 Network Configuration

KVStorm requires the following network ports:

- **9090**: Client API (gRPC)
- **9091**: Inter-node communication (gRPC)
- **9092**: Admin API (HTTP/REST)
- **9093**: Metrics endpoint (Prometheus format)
- **9094**: Change stream endpoint (gRPC)

All inter-node communication should use a dedicated network segment to avoid interference with client traffic. We recommend configuring jumbo frames (MTU 9000) on the inter-node network for optimal throughput.

### 8.3 Monitoring and Alerting

KVStorm exports metrics in Prometheus format on the `/metrics` endpoint. Key metrics to monitor include:

- `kvstorm_operations_total` - Total operations by type and consistency level
- `kvstorm_latency_seconds` - Operation latency histogram
- `kvstorm_replication_lag_seconds` - Replication lag per partition
- `kvstorm_disk_usage_bytes` - Disk usage per node
- `kvstorm_compaction_pending` - Number of pending compaction tasks
- `kvstorm_gossip_members` - Number of known cluster members
- `kvstorm_hint_queue_size` - Number of pending hinted handoffs
- `kvstorm_cache_hit_ratio` - L1 cache hit ratio per node

Recommended alerting thresholds:

- p99 latency > 10 ms: Warning
- p99 latency > 50 ms: Critical
- Replication lag > 30 seconds: Warning
- Replication lag > 120 seconds: Critical
- Disk usage > 75%: Warning
- Disk usage > 90%: Critical
- Cache hit ratio < 80%: Warning

### 8.4 Capacity Planning

When planning capacity, consider the following formula:

```
Required nodes = (Total data size * Replication factor) / (Usable storage per node)
Usable storage per node = Raw storage * 0.65
```

The 0.65 factor accounts for LSM-tree space amplification, WAL overhead, and operational headroom. For example, to store 10 TB of data with a replication factor of 3 on nodes with 2 TB of storage:

```
Required nodes = (10 TB * 3) / (2 TB * 0.65) = 23.1 ≈ 24 nodes
```

We recommend adding 10-15% additional nodes beyond the calculated minimum to handle traffic spikes and rolling maintenance operations.

### 8.5 Rolling Upgrades

KVStorm supports rolling upgrades with zero downtime. The upgrade process is:

1. Verify the new version is compatible using the pre-upgrade check tool
2. Drain traffic from the target node using the admin API
3. Stop the KVStorm process gracefully (SIGTERM with 30s grace period)
4. Replace the binary and update configuration if needed
5. Start the process with the new binary
6. Wait for the node to rejoin the cluster and pass health checks
7. Re-enable traffic to the node
8. Move to the next node, waiting at least 60 seconds between nodes

The system maintains backward compatibility for the wire protocol across two major versions. Major version upgrades that break compatibility require a coordinated blue-green deployment.

## 9. Security Considerations

### 9.1 Authentication

KVStorm supports mutual TLS (mTLS) for both client-to-node and node-to-node communication. All nodes and clients must present valid certificates signed by a trusted certificate authority.

### 9.2 Authorization

A simple role-based access control (RBAC) system is provided:

- **Admin**: Full access to all operations and configuration
- **Writer**: Can read and write keys
- **Reader**: Can only read keys

Roles are assigned at the namespace level, allowing fine-grained access control. Role assignments are stored in the cluster metadata and replicated to all nodes.

### 9.3 Encryption

All data in transit is encrypted using TLS 1.2. Data at rest encryption is supported through filesystem-level encryption (e.g., LUKS, dm-crypt) but is not handled by KVStorm directly.

## 10. Open Questions

The following questions remain unresolved and require further discussion:

1. Should we support secondary indexes? This would significantly complicate the design but would enable more flexible query patterns.
2. What is the migration strategy from the existing Redis cluster? The current proposal is a dual-write period with traffic shadowing, followed by gradual cutover.
3. How do we handle clock skew in last-write-wins conflict resolution? We plan to use NTP with a bounded skew assumption of 50ms, but this needs validation.
4. What is the budget for the initial deployment? This will determine the cluster size and hardware specifications.

## 11. Timeline

| Milestone | Target Date | Description |
|-----------|-------------|-------------|
| Design Review Complete | February 20, 2026 | Incorporate all reviewer feedback |
| Prototype | March 30, 2026 | Working prototype with core read/write path |
| Storage Engine Benchmark | April 15, 2026 | Validate storage engine performance claims |
| Alpha Release | May 15, 2026 | Feature-complete alpha for internal testing |
| Shadow Traffic Test | June 15, 2026 | Run shadow traffic from production Redis |
| Beta Release | August 1, 2026 | Beta release with production hardening |
| GA Release | October 1, 2026 | General availability |

## 12. References

1. DeCandia, G., et al. "Dynamo: Amazon's Highly Available Key-value Store." SOSP 2007.
2. Chang, F., et al. "Bigtable: A Distributed Storage System for Structured Data." OSDI 2006.
3. Lakshman, A., and Malik, P. "Cassandra: A Decentralized Structured Storage System." LADIS 2009.
4. Ongaro, D., and Ousterhout, J. "In Search of an Understandable Consensus Algorithm." USENIX ATC 2014.
5. Meta Engineering. "RocksDB: A Persistent Key-Value Store for Flash and RAM Storage."
6. Kulkarni, S., et al. "Logical Physical Clocks and Consistent Snapshots in Globally Distributed Databases." OPODIS 2014.
7. Einziger, G., et al. "TinyLFU: A Highly Efficient Cache Admission Policy." ACM ToCS 2017.

---

*This document is confidential and intended for internal use only. Please direct feedback to the #kvstorm-design Slack channel.*
