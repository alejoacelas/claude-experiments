#!/usr/bin/env python3
"""
Generate gold-standard expected outputs for each task.

For tasks where the expected output can be precisely defined,
this script generates it programmatically. For others, it
provides a starting point that may need manual refinement.
"""

import json
import os
import re
import shutil
import sys

PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(PROJ_ROOT, 'documents')
TASKS_DIR = os.path.join(PROJ_ROOT, 'tasks')


def read_file(path):
    with open(path) as f:
        return f.read()


def write_file(path, content):
    with open(path, 'w') as f:
        f.write(content)
    print(f"  Written: {path}")


def generate_task1_gold():
    """
    Task 1: Apply only formatting/citation changes from v2 to v1.
    - booktabs package
    - Date change
    - Table formatting (hline -> toprule/midrule/bottomrule, @{} columns)
    - En-dash fixes (12-18 -> 12--18)
    - Number formatting with \,
    """
    v1 = read_file(os.path.join(DOCS_DIR, 'paper_v1.tex'))

    # Add booktabs package
    v1 = v1.replace(
        '\\usepackage{algorithmic}\n',
        '\\usepackage{algorithmic}\n\\usepackage{booktabs}\n'
    )

    # Date change
    v1 = v1.replace('\\date{October 2025}', '\\date{January 2026}')

    # En-dash fixes in abstract and contributions
    v1 = v1.replace('12-18\\%', '12--18\\%')
    # Also fix 12-18% in contributions
    v1 = v1.replace('12-18\\% improvement', '12--18\\% improvement')

    # Table 1: Standard benchmarks - update formatting
    v1 = v1.replace(
        '\\begin{tabular}{lccc}\n\\hline\nMethod & Split-CIFAR100 & Permuted-MNIST & Split-miniImageNet \\\\\n\\hline',
        '\\begin{tabular}{@{}lccc@{}}\n\\toprule\nMethod & Split-CIFAR100 & Permuted-MNIST & Split-miniImageNet \\\\\n\\midrule'
    )
    v1 = v1.replace(
        'CLS-ER & 63.5 $\\pm$ 0.7 & 91.3 $\\pm$ 0.3 & 58.9 $\\pm$ 0.8 \\\\\n\\hline\nAMN (Ours)',
        'CLS-ER & 63.5 $\\pm$ 0.7 & 91.3 $\\pm$ 0.3 & 58.9 $\\pm$ 0.8 \\\\\n\\midrule\nAMN (Ours)'
    )
    v1 = v1.replace(
        'AMN (Ours) & \\textbf{72.1} $\\pm$ \\textbf{0.6} & \\textbf{94.8} $\\pm$ \\textbf{0.2} & \\textbf{68.4} $\\pm$ \\textbf{0.7} \\\\\n\\hline\n\\end{tabular}',
        'AMN (Ours) & \\textbf{72.1} $\\pm$ \\textbf{0.6} & \\textbf{94.8} $\\pm$ \\textbf{0.2} & \\textbf{68.4} $\\pm$ \\textbf{0.7} \\\\\n\\bottomrule\n\\end{tabular}'
    )

    # Table 2: StreamingWorld - update formatting
    v1 = v1.replace(
        '\\begin{tabular}{lccc}\n\\hline\nMethod & SW-Easy & SW-Medium & SW-Hard \\\\\n\\hline',
        '\\begin{tabular}{@{}lccc@{}}\n\\toprule\nMethod & SW-Easy & SW-Medium & SW-Hard \\\\\n\\midrule'
    )
    v1 = v1.replace(
        'CLS-ER & 69.7 $\\pm$ 0.9 & 58.6 $\\pm$ 1.1 & 42.1 $\\pm$ 1.4 \\\\\n\\hline\nAMN (Ours) & \\textbf{81.3}',
        'CLS-ER & 69.7 $\\pm$ 0.9 & 58.6 $\\pm$ 1.1 & 42.1 $\\pm$ 1.4 \\\\\n\\midrule\nAMN (Ours) & \\textbf{81.3}'
    )
    v1 = v1.replace(
        '\\textbf{58.9} $\\pm$ \\textbf{1.0} \\\\\n\\hline\n\\end{tabular}\n\\end{table}\n\nThe results on StreamingWorld are particularly notable',
        '\\textbf{58.9} $\\pm$ \\textbf{1.0} \\\\\n\\bottomrule\n\\end{tabular}\n\\end{table}\n\nThe results on StreamingWorld are particularly notable'
    )

    # Table 3: Ablation - update formatting
    v1 = v1.replace(
        '\\begin{tabular}{lcc}\n\\hline\nVariant & Split-CIFAR100 & SW-Hard \\\\\n\\hline',
        '\\begin{tabular}{@{}lcc@{}}\n\\toprule\nVariant & Split-CIFAR100 & SW-Hard \\\\\n\\midrule'
    )
    v1 = v1.replace(
        '$-$ Memory utilization loss & 70.8 & 56.3 \\\\\n$-$ EWC regularization & 71.2 & 57.1 \\\\\n\\hline\n\\end{tabular}',
        '$-$ Memory utilization loss & 70.8 & 56.3 \\\\\n$-$ EWC regularization & 71.2 & 57.1 \\\\\n\\bottomrule\n\\end{tabular}'
    )

    # Number formatting: 5000 -> 5,000, etc.  (v2 uses 5,000)
    v1 = v1.replace('buffer size 5000)', 'buffer size 5,000)')
    v1 = v1.replace('(buffer size 5000)', '(buffer size 5,000)')

    # Fix \, spacing for units: 4 MB -> 4\\,MB, 15 MB -> 15\\,MB, 20 MB -> 20\\,MB
    v1 = v1.replace('approximately 4 MB', 'approximately 4\\,MB')
    v1 = v1.replace('approximately 15 MB', 'approximately 15\\,MB')
    v1 = v1.replace('approximately 20 MB', 'approximately 20\\,MB')
    v1 = v1.replace('4 MB vs. 100+ MB', '4\\,MB vs.\\ 100+\\,MB')

    # Fix S.C. -> S.C.\ and P.R. -> P.R.\
    v1 = v1.replace('S.C. is', 'S.C.\\ is')
    v1 = v1.replace('P.R. is', 'P.R.\\ is')

    return v1


def generate_task4_gold():
    """
    Task 4: Apply all changes EXCEPT in the Experiments section.
    Start with v2 and replace the Experiments section with v1's version.
    """
    v1 = read_file(os.path.join(DOCS_DIR, 'paper_v1.tex'))
    v2 = read_file(os.path.join(DOCS_DIR, 'paper_v2.tex'))

    # Extract experiments section from v1
    # From \section{Experiments} to \section{Analysis and Discussion}
    v1_exp_match = re.search(
        r'(\\section\{Experiments\}.*?)(?=\\section\{Analysis)',
        v1, re.DOTALL
    )
    v2_exp_match = re.search(
        r'(\\section\{Experiments\}.*?)(?=\\section\{Analysis)',
        v2, re.DOTALL
    )

    if v1_exp_match and v2_exp_match:
        result = v2.replace(v2_exp_match.group(1), v1_exp_match.group(1))
    else:
        print("  WARNING: Could not find Experiments section boundaries!")
        result = v2

    return result


def generate_task5_gold():
    """
    Task 5: Cherry-pick specific numbered changes.
    This requires running doccompare and applying the specific changes.
    We'll construct this by carefully applying changes from v2 to v1.
    """
    # This is the most mechanical task - apply specific changes by number.
    # For the gold standard, we'll note which changes correspond to which edits
    # and build the expected output.
    #
    # Changes to apply: 1, 3, 5, 6, 8, 9, 15, 17, 18, 19, 20, 29, 36,
    #                   50, 51, 52, 53, 63, 64, 65, 71, 72, 73, 75, 76
    #
    # These include:
    # 1: metadata changes (new author, date, booktabs)
    # 3: Intro para 1 wording tweaks
    # 5-6: New "Motivation and Key Insight" subsection
    # 8: "also known as" -> "also referred to as"
    # 9: Contributions list update
    # 15: Architecture overview - "three" -> "four" components
    # 17-20: Task Context Estimator (heading + content + equation + description)
    # 29: Consolidation proof reference fix
    # 36: Algorithm update
    # 50-53: Scaling to Long Task Sequences (heading + 3 blocks)
    # 63-65: Role of Task Context Estimator (heading + 2 blocks)
    # 71-73: Conclusion changes
    # 75: New future work paragraph
    # 76: Acknowledgments update

    v1 = read_file(os.path.join(DOCS_DIR, 'paper_v1.tex'))
    v2 = read_file(os.path.join(DOCS_DIR, 'paper_v2.tex'))

    # This task's gold standard is complex to generate programmatically
    # because it requires inserting v2 content at specific positions in v1.
    # We'll create it by starting with v1 and carefully applying each change.

    result = v1

    # Change 1: Metadata (add booktabs, new author, date)
    result = result.replace(
        '\\usepackage{algorithmic}\n',
        '\\usepackage{algorithmic}\n\\usepackage{booktabs}\n'
    )

    result = result.replace(
        '  Priya Ramanathan \\\\\n  MIT CSAIL\\\\\n  Cambridge, MA\\\\\n  \\texttt{priya@mit.edu}\n}\n\\date{October 2025}',
        '  Priya Ramanathan \\\\\n  MIT CSAIL\\\\\n  Cambridge, MA\\\\\n  \\texttt{priya@mit.edu}\n  \\and\n  James O\'Sullivan \\\\\n  University of Toronto\\\\\n  Toronto, Canada\\\\\n  \\texttt{josullivan@utoronto.ca}\n}\n\\date{January 2026}'
    )

    # Change 3: Intro para 1 - small wording changes
    result = result.replace(
        'Human brains can seamlessly integrate',
        'Human brains seamlessly integrate'
    )
    result = result.replace(
        'where training on new tasks can severely degrade',
        'where training on new tasks severely degrades'
    )

    # Changes 5-6: Add "Motivation and Key Insight" subsection after intro para 2
    motivation_section = """
\\subsection{Motivation and Key Insight}

Before discussing prior approaches, we highlight the key observation that motivates our work. Existing continual learning methods typically treat all learned representations as equally important, applying uniform protection or replay strategies. However, in practice, some representations serve as ``bridges'' between tasks---capturing shared structure that facilitates transfer---while others are task-specific and prone to causing interference. This asymmetry suggests that an adaptive, representation-aware approach to memory management should outperform uniform strategies.
"""
    result = result.replace(
        'a learning system must be stable enough to retain useful knowledge but plastic enough to learn from new experiences.\n\nExisting approaches',
        'a learning system must be stable enough to retain useful knowledge but plastic enough to learn from new experiences.\n' + motivation_section + '\nExisting approaches'
    )

    # Change 8: "also known as" -> "also referred to as"
    result = result.replace('also known as', 'also referred to as')

    # Change 9: Add new contribution bullet
    result = result.replace(
        '    \\item We introduce StreamingWorld, a challenging benchmark',
        '    \\item We introduce StreamingWorld, a challenging benchmark'
    )
    result = result.replace(
        '    \\item We demonstrate state-of-the-art results across multiple benchmarks, achieving 12-18\\% improvement in average accuracy over existing methods.\n\\end{itemize}',
        '    \\item We conduct extensive scaling experiments demonstrating AMN\'s robustness to long task sequences (50+ tasks), a regime where most existing methods fail.\n    \\item We demonstrate state-of-the-art results across multiple benchmarks, achieving 12--18\\% improvement in average accuracy over existing methods.\n\\end{itemize}'
    )

    # Change 15: Architecture overview - "three" -> "four", add task context estimator
    result = result.replace(
        'AMN consists of three main components: (1) a feature extractor $f_\\theta$, (2) an external memory module $\\mathcal{M}$, and (3) a task-adaptive classifier $g_\\phi$. The feature extractor maps inputs to a shared representation space. The memory module stores and retrieves compressed representations. The classifier produces predictions conditioned on both the input representation and retrieved memories.',
        'AMN consists of four main components: (1) a feature extractor $f_\\theta$, (2) an external memory module $\\mathcal{M}$, (3) a task context estimator $h_\\psi$, and (4) a task-adaptive classifier $g_\\phi$. The feature extractor maps inputs to a shared representation space. The memory module stores and retrieves compressed representations. The task context estimator infers a soft task descriptor from recent inputs. The classifier produces predictions conditioned on both the input representation and retrieved memories.'
    )

    # Changes 17-20: Add Task Context Estimator subsection
    tce_section = """
\\subsubsection{Task Context Estimator}

The task context estimator $h_\\psi$ is a lightweight recurrent module that processes a sliding window of recent input representations to produce a task context vector $c_t \\in \\mathbb{R}^{d_c}$:
\\begin{equation}
    c_t = h_\\psi(z_{t-W:t})
\\end{equation}
where $W$ is the window size. This context vector modulates the memory retrieval process, allowing AMN to adapt its memory access patterns to the current task regime without requiring explicit task labels.
"""
    result = result.replace(
        '\\subsubsection{External Memory Module}',
        tce_section + '\n\\subsubsection{External Memory Module}'
    )

    # Change 29: Fix appendix reference
    result = result.replace(
        'The proof is provided in Appendix A.',
        'The proof is provided in Appendix~\\ref{app:proof}.'
    )

    # Change 36: Update algorithm caption
    result = result.replace(
        '\\caption{AMN Training}',
        '\\caption{AMN Training Procedure}'
    )

    # Changes 50-53: Add Scaling to Long Task Sequences subsection
    scaling_section = """
\\subsection{Scaling to Long Task Sequences}

A critical question for practical deployment is how continual learning methods perform as the number of tasks grows. We evaluate all methods on StreamingWorld with sequences of 10, 25, 50, and 100 tasks.

\\begin{table}[h]
\\centering
\\caption{Average accuracy (\\%) on StreamingWorld-Medium as a function of the number of tasks in the sequence.}
\\label{tab:scaling}
\\begin{tabular}{@{}lcccc@{}}
\\toprule
Method & 10 tasks & 25 tasks & 50 tasks & 100 tasks \\\\
\\midrule
EWC & 38.7 $\\pm$ 2.1 & 29.4 $\\pm$ 2.8 & 18.2 $\\pm$ 3.1 & 11.5 $\\pm$ 3.4 \\\\
ER & 51.4 $\\pm$ 1.5 & 44.2 $\\pm$ 1.9 & 35.7 $\\pm$ 2.2 & 27.3 $\\pm$ 2.6 \\\\
CLS-ER & 58.6 $\\pm$ 1.1 & 50.1 $\\pm$ 1.4 & 40.8 $\\pm$ 1.7 & 32.9 $\\pm$ 2.0 \\\\
L2P & 59.8 $\\pm$ 1.0 & 51.3 $\\pm$ 1.3 & 41.5 $\\pm$ 1.6 & 33.7 $\\pm$ 1.9 \\\\
\\midrule
AMN (Ours) & \\textbf{72.4} $\\pm$ \\textbf{0.8} & \\textbf{67.8} $\\pm$ \\textbf{0.9} & \\textbf{62.1} $\\pm$ \\textbf{1.1} & \\textbf{56.4} $\\pm$ \\textbf{1.3} \\\\
\\bottomrule
\\end{tabular}
\\end{table}

AMN demonstrates substantially better scaling behavior. While baseline methods lose 40--70\\% of their 10-task accuracy when scaling to 100 tasks, AMN retains 78\\% of its accuracy. This robustness stems from the consolidation mechanism, which actively prevents memory interference even as the number of stored representations grows.
"""
    result = result.replace(
        '\\subsection{Ablation Studies}',
        scaling_section + '\n\\subsection{Ablation Studies}'
    )

    # Changes 63-65: Add Role of Task Context Estimator subsection
    role_section = """
\\subsection{Role of the Task Context Estimator}

The task context estimator provides significant benefits beyond what is captured by the ablation numbers alone. By analyzing the learned context representations, we find that the estimator:
\\begin{enumerate}
    \\item Detects distribution shifts approximately 2--3 mini-batches before they become apparent in the loss signal.
    \\item Produces context vectors that naturally cluster by task regime, even without explicit task labels.
    \\item Enables the gating mechanism to smoothly transition between relying on memory versus current input, with memory reliance increasing during task transitions.
\\end{enumerate}
"""
    result = result.replace(
        '\\subsection{Comparison with Biological Memory}',
        role_section + '\n\\subsection{Comparison with Biological Memory}'
    )

    # Change 71: Conclusion rewrite
    result = result.replace(
        'We have presented Adaptive Memory Networks (AMN), a novel approach to continual learning that combines an external memory module with biologically-inspired consolidation. AMN addresses the stability-plasticity dilemma through adaptive memory management, with selective retrieval via learned attention and periodic consolidation to minimize interference. Our experimental results demonstrate state-of-the-art performance across standard benchmarks and the newly introduced StreamingWorld benchmark.',
        'We have presented Adaptive Memory Networks (AMN), a novel approach to continual learning that integrates an external memory module with biologically-inspired consolidation and a learned task context estimator. AMN addresses the stability-plasticity dilemma through three complementary mechanisms: adaptive memory management with importance-weighted replacement, selective retrieval via context-modulated attention, and periodic consolidation to minimize inter-task interference.'
    )

    # Change 72: Add new paragraph in conclusion
    new_conclusion_para = "\nOur experimental results demonstrate consistent state-of-the-art performance across standard benchmarks and the newly introduced StreamingWorld benchmark, with particularly strong results in challenging settings involving long task sequences, abrupt distribution shifts, and class imbalance. The scaling experiments reveal that AMN maintains robust performance even with 100-task sequences, a regime where existing methods suffer severe degradation.\n"
    result = result.replace(
        'and periodic consolidation to minimize inter-task interference.\n\nKey findings',
        'and periodic consolidation to minimize inter-task interference.\n' + new_conclusion_para + '\nKey findings'
    )

    # Change 73: Key findings update
    result = result.replace(
        'Key findings include the critical importance of the consolidation mechanism for handling complex distribution shifts, the emergence of ``bridge\'\' memory representations that facilitate cross-task transfer, and the memory efficiency advantages of storing compressed representations over raw samples.',
        'Key findings include the critical importance of the consolidation mechanism for managing complex distribution shifts, the value of task context estimation for adaptive memory retrieval, the emergence of bridge memory representations that facilitate cross-task transfer, and the memory efficiency advantages of storing compressed representations over raw samples.'
    )

    # Change 75: New future work paragraph (replace the old one)
    result = result.replace(
        'Future work will explore several promising directions: adaptive memory sizing based on task complexity, extension to multi-modal continual learning, and investigation of multi-timescale consolidation strategies that more closely mirror biological memory systems. We believe that drawing deeper connections between artificial and biological memory systems will continue to yield advances in continual learning.',
        'Future work will pursue several promising directions: adaptive memory sizing driven by task complexity signals, extension to multi-modal continual learning, investigation of multi-timescale consolidation strategies that more closely mirror biological memory systems, and exploration of federated continual learning settings where memory must be consolidated across distributed agents. We believe that continued cross-pollination between neuroscience and machine learning will yield further advances in building systems that learn continuously and robustly.'
    )

    # Change 76: Acknowledgments update
    result = result.replace(
        'We thank the anonymous reviewers for their constructive feedback. This work was supported by NSF Grant IIS-2023456, the DARPA Lifelong Learning Machines program, and computing resources from Google Cloud. S.C. is supported by a Stanford Graduate Fellowship. P.R. is supported by an NSF CAREER award.',
        'We thank the anonymous reviewers for their insightful feedback, which significantly improved this paper. We also thank Elena Voronova for helpful discussions on the biological plausibility of our consolidation mechanism. This work was supported by NSF Grant IIS-2023456, the DARPA Lifelong Learning Machines program, a Google Research Award, and computing resources provided by Google Cloud and the Vector Institute. S.C.\\ is supported by a Stanford Graduate Fellowship. P.R.\\ is supported by an NSF CAREER award. J.O.\\ is supported by a CIFAR AI Chair.'
    )

    return result


def main():
    print("Generating gold-standard outputs...")
    print()

    # Task 1
    print("Task 1: Formatting-only changes")
    gold = generate_task1_gold()
    gold_path = os.path.join(TASKS_DIR, 'task1', 'expected_output.tex')
    write_file(gold_path, gold)

    # Task 2: This requires manual construction as it's about adding v2 content to v1
    # For now, generate a placeholder
    print("\nTask 2: All additions, no removals")
    print("  (Complex task - generating best approximation)")
    # Start with v1, insert all added blocks from v2
    v1 = read_file(os.path.join(DOCS_DIR, 'paper_v1.tex'))
    # For task 2, the gold is v1 with all v2 additions inserted
    # This is essentially "v1 + new content from v2"
    # Use task5 generation as a base since it covers most additions
    gold2 = v1  # Start with v1 unchanged

    # Add booktabs (this is in metadata change, but since we keep v1 for modified blocks,
    # we actually should NOT change the preamble. However the new author IS an addition.)
    # Actually for task 2: add all NEW content but don't modify existing.
    # New author is an addition to existing block, which is tricky.
    # Let's handle the clear additions:

    # New author (added to existing block - this is technically a modification but the task says add new author)
    gold2 = gold2.replace(
        '  \\texttt{priya@mit.edu}\n}\n\\date{October 2025}',
        '  \\texttt{priya@mit.edu}\n  \\and\n  James O\'Sullivan \\\\\n  University of Toronto\\\\\n  Toronto, Canada\\\\\n  \\texttt{josullivan@utoronto.ca}\n}\n\\date{October 2025}'
    )

    # New sentence in abstract about scaling
    gold2 = gold2.replace(
        'while maintaining a compact memory footprint. Furthermore,',
        'while maintaining a compact memory footprint. We additionally show that AMN scales effectively to longer task sequences with 50+ tasks, maintaining consistent performance where baselines degrade significantly. Furthermore,'
    )

    # New Motivation subsection
    gold2 = gold2.replace(
        'a learning system must be stable enough to retain useful knowledge but plastic enough to learn from new experiences.\n\nExisting approaches',
        'a learning system must be stable enough to retain useful knowledge but plastic enough to learn from new experiences.\n\n\\subsection{Motivation and Key Insight}\n\nBefore discussing prior approaches, we highlight the key observation that motivates our work. Existing continual learning methods typically treat all learned representations as equally important, applying uniform protection or replay strategies. However, in practice, some representations serve as ``bridges\'\' between tasks---capturing shared structure that facilitates transfer---while others are task-specific and prone to causing interference. This asymmetry suggests that an adaptive, representation-aware approach to memory management should outperform uniform strategies.\n\nExisting approaches'
    )

    # New contribution bullet point
    gold2 = gold2.replace(
        '    \\item We demonstrate state-of-the-art results',
        '    \\item We conduct extensive scaling experiments demonstrating AMN\'s robustness to long task sequences (50+ tasks), a regime where most existing methods fail.\n    \\item We demonstrate state-of-the-art results'
    )

    # New Task Context Estimator subsection
    tce = """\\subsubsection{Task Context Estimator}

The task context estimator $h_\\psi$ is a lightweight recurrent module that processes a sliding window of recent input representations to produce a task context vector $c_t \\in \\mathbb{R}^{d_c}$:
\\begin{equation}
    c_t = h_\\psi(z_{t-W:t})
\\end{equation}
where $W$ is the window size. This context vector modulates the memory retrieval process, allowing AMN to adapt its memory access patterns to the current task regime without requiring explicit task labels.

"""
    gold2 = gold2.replace(
        '\\subsubsection{External Memory Module}',
        tce + '\\subsubsection{External Memory Module}'
    )

    # New contrastive loss content
    ctx_loss = """
The task context contrastive loss is:
\\begin{equation}
    \\mathcal{L}_{\\text{ctx}} = -\\log \\frac{\\exp(c_t^\\top c_t^+ / \\kappa)}{\\exp(c_t^\\top c_t^+ / \\kappa) + \\sum_{c^-} \\exp(c_t^\\top c^- / \\kappa)}
\\end{equation}
where $c_t^+$ is a context vector from the same task regime, $c^-$ are context vectors from different regimes, and $\\kappa$ is a temperature parameter.
"""
    gold2 = gold2.replace(
        'Algorithm~\\ref{alg:training} summarizes',
        ctx_loss + '\nAlgorithm~\\ref{alg:training} summarizes'
    )

    # New Scaling subsection
    scaling = """\\subsection{Scaling to Long Task Sequences}

A critical question for practical deployment is how continual learning methods perform as the number of tasks grows. We evaluate all methods on StreamingWorld with sequences of 10, 25, 50, and 100 tasks.

\\begin{table}[h]
\\centering
\\caption{Average accuracy (\\%) on StreamingWorld-Medium as a function of the number of tasks in the sequence.}
\\label{tab:scaling}
\\begin{tabular}{@{}lcccc@{}}
\\toprule
Method & 10 tasks & 25 tasks & 50 tasks & 100 tasks \\\\
\\midrule
EWC & 38.7 $\\pm$ 2.1 & 29.4 $\\pm$ 2.8 & 18.2 $\\pm$ 3.1 & 11.5 $\\pm$ 3.4 \\\\
ER & 51.4 $\\pm$ 1.5 & 44.2 $\\pm$ 1.9 & 35.7 $\\pm$ 2.2 & 27.3 $\\pm$ 2.6 \\\\
CLS-ER & 58.6 $\\pm$ 1.1 & 50.1 $\\pm$ 1.4 & 40.8 $\\pm$ 1.7 & 32.9 $\\pm$ 2.0 \\\\
L2P & 59.8 $\\pm$ 1.0 & 51.3 $\\pm$ 1.3 & 41.5 $\\pm$ 1.6 & 33.7 $\\pm$ 1.9 \\\\
\\midrule
AMN (Ours) & \\textbf{72.4} $\\pm$ \\textbf{0.8} & \\textbf{67.8} $\\pm$ \\textbf{0.9} & \\textbf{62.1} $\\pm$ \\textbf{1.1} & \\textbf{56.4} $\\pm$ \\textbf{1.3} \\\\
\\bottomrule
\\end{tabular}
\\end{table}

AMN demonstrates substantially better scaling behavior. While baseline methods lose 40--70\\% of their 10-task accuracy when scaling to 100 tasks, AMN retains 78\\% of its accuracy. This robustness stems from the consolidation mechanism, which actively prevents memory interference even as the number of stored representations grows.

"""
    gold2 = gold2.replace(
        '\\subsection{Ablation Studies}',
        scaling + '\\subsection{Ablation Studies}'
    )

    # New memory efficiency paragraph
    gold2 = gold2.replace(
        "AMN's advantage becomes more pronounced: 4 MB vs. 100+ MB for raw sample storage.\n\n\\subsection{Consolidation Dynamics}",
        "AMN's advantage becomes more pronounced: 4 MB vs. 100+ MB for raw sample storage.\n\nImportantly, AMN's memory footprint remains constant regardless of input resolution, since it stores fixed-dimensional representations rather than raw data. This property makes AMN particularly attractive for high-resolution and multi-modal applications.\n\n\\subsection{Consolidation Dynamics}"
    )

    # New Role of Task Context Estimator subsection
    role = """\\subsection{Role of the Task Context Estimator}

The task context estimator provides significant benefits beyond what is captured by the ablation numbers alone. By analyzing the learned context representations, we find that the estimator:
\\begin{enumerate}
    \\item Detects distribution shifts approximately 2--3 mini-batches before they become apparent in the loss signal.
    \\item Produces context vectors that naturally cluster by task regime, even without explicit task labels.
    \\item Enables the gating mechanism to smoothly transition between relying on memory versus current input, with memory reliance increasing during task transitions.
\\end{enumerate}

"""
    gold2 = gold2.replace(
        '\\subsection{Comparison with Biological Memory}',
        role + '\\subsection{Comparison with Biological Memory}'
    )

    # New conclusion paragraph
    gold2 = gold2.replace(
        'Our experimental results demonstrate state-of-the-art performance across standard benchmarks and the newly introduced StreamingWorld benchmark.\n\nKey findings',
        'Our experimental results demonstrate state-of-the-art performance across standard benchmarks and the newly introduced StreamingWorld benchmark.\n\nOur experimental results demonstrate consistent state-of-the-art performance across standard benchmarks and the newly introduced StreamingWorld benchmark, with particularly strong results in challenging settings involving long task sequences, abrupt distribution shifts, and class imbalance. The scaling experiments reveal that AMN maintains robust performance even with 100-task sequences, a regime where existing methods suffer severe degradation.\n\nKey findings'
    )

    # Elena acknowledgment and new funding
    gold2 = gold2.replace(
        'We thank the anonymous reviewers for their constructive feedback. This work was supported by NSF Grant IIS-2023456, the DARPA Lifelong Learning Machines program, and computing resources from Google Cloud. S.C. is supported by a Stanford Graduate Fellowship. P.R. is supported by an NSF CAREER award.',
        'We thank the anonymous reviewers for their constructive feedback. We also thank Elena Voronova for helpful discussions on the biological plausibility of our consolidation mechanism. This work was supported by NSF Grant IIS-2023456, the DARPA Lifelong Learning Machines program, a Google Research Award, and computing resources provided by Google Cloud and the Vector Institute. S.C. is supported by a Stanford Graduate Fellowship. P.R. is supported by an NSF CAREER award. J.O. is supported by a CIFAR AI Chair.'
    )

    # StreamingWorld URL
    gold2 = gold2.replace(
        'The benchmark will be publicly released upon paper acceptance, along with evaluation code and pretrained models.',
        'The benchmark will be publicly released upon paper acceptance, along with evaluation code and pretrained models.\n\nThe benchmark, including evaluation code, data loaders, and pretrained baseline models, is publicly available at \\url{https://github.com/streamingworld-benchmark/streamingworld}.'
    )

    write_file(os.path.join(TASKS_DIR, 'task2', 'expected_output.tex'), gold2)

    # Task 3: Copyediting only
    print("\nTask 3: Copyediting-only changes")
    gold3 = v1

    # Tense and small wording changes
    gold3 = gold3.replace(
        'Human brains can seamlessly integrate',
        'Human brains seamlessly integrate'
    )
    gold3 = gold3.replace(
        'where training on new tasks can severely degrade',
        'where training on new tasks severely degrades'
    )
    gold3 = gold3.replace(
        'also known as lifelong',
        'also referred to as lifelong'
    )
    gold3 = gold3.replace(
        'leading to scalability concerns',
        'which raises scalability concerns'
    )
    gold3 = gold3.replace(
        'raising both privacy concerns',
        'which raises both privacy concerns'
    )
    gold3 = gold3.replace(
        'AMN includes a memory consolidation process',
        'AMN incorporates a memory consolidation process'
    )
    gold3 = gold3.replace(
        'during training and inference',
        'during both training and inference'
    )
    gold3 = gold3.replace(
        'use attention-based mechanisms',
        'employed attention-based mechanisms'
    )
    gold3 = gold3.replace(
        'maintain performance across',
        'maintain good performance across'
    )
    gold3 = gold3.replace(
        'shifts gradually and unpredictably',
        'may shift gradually and unpredictably'
    )
    gold3 = gold3.replace(
        'use a standard ResNet-18',
        'use a ResNet-18'
    )
    gold3 = gold3.replace(
        'though any differentiable encoder can be used',
        'though any differentiable encoder can be substituted'
    )
    gold3 = gold3.replace(
        'normalized to lie on the unit hypersphere: $z = f_\\theta(x) / \\|f_\\theta(x)\\|$',
        '$\\ell_2$-normalized to lie on the unit hypersphere: $z = f_\\theta(x) / \\|f_\\theta(x)\\|_2$'
    )
    gold3 = gold3.replace(
        'the running average of attention weights',
        'the exponential moving average of attention weights'
    )
    gold3 = gold3.replace(
        'are overwritten.',
        'are candidates for overwriting.'
    )
    gold3 = gold3.replace(
        'memory keys are becoming too similar, potentially leading to retrieval errors.',
        'memory keys have become too similar, which can lead to retrieval errors and cross-task confusion.'
    )
    gold3 = gold3.replace(
        'we perform the following optimization:',
        'we solve the following optimization problem:'
    )
    gold3 = gold3.replace(
        ', ensuring efficient convergence.',
        ', which guarantees efficient convergence to a unique minimizer.'
    )
    gold3 = gold3.replace(
        'may not reflect the complexity',
        'fail to capture the complexity'
    )
    gold3 = gold3.replace(
        'The proof is provided in Appendix A.',
        'The proof is provided in Appendix~\\ref{app:proof}.'
    )
    # En-dash fixes
    gold3 = gold3.replace('12-18\\%', '12--18\\%')

    write_file(os.path.join(TASKS_DIR, 'task3', 'expected_output.tex'), gold3)

    # Task 4
    print("\nTask 4: Everything except Experiments")
    gold4 = generate_task4_gold()
    write_file(os.path.join(TASKS_DIR, 'task4', 'expected_output.tex'), gold4)

    # Task 5
    print("\nTask 5: Cherry-picked changes")
    gold5 = generate_task5_gold()
    write_file(os.path.join(TASKS_DIR, 'task5', 'expected_output.tex'), gold5)

    print("\nDone! Gold standards generated for all 5 tasks.")
    print("Note: Tasks 2 and 3 gold outputs may need manual refinement.")


if __name__ == '__main__':
    main()
