/**
 * OneDrive Revision Shortcuts Content Script
 *
 * Adds keyboard shortcuts for OneDrive revision controls:
 * - Ctrl + [ : Accept Revision
 * - Ctrl + ] : Reject Revision
 * - Ctrl + ' : Previous Revision
 * - Ctrl + \ : Next Revision
 */

(function() {
  'use strict';

  // Detect which frame we're in
  const isIframe = window !== window.top;
  const frameInfo = isIframe ? `[iframe: ${window.location.hostname}]` : '[main page]';

  console.log(`OneDrive Revision Shortcuts extension loaded ${frameInfo}`);

  // Constants for retry logic
  const RETRY_INTERVAL_MS = 500;
  const MAX_RETRY_DURATION_MS = 3000;
  const MAX_RETRIES = MAX_RETRY_DURATION_MS / RETRY_INTERVAL_MS; // 6 retries

  /**
   * Find a button by its icon name using multiple selector strategies
   * @param {string} iconName - The icon name to search for (e.g., "AcceptRevision_24")
   * @returns {HTMLElement|null} - The clickable parent element or null if not found
   */
  function findButtonByIcon(iconName) {
    // Strategy 1: Try iconname attribute (case-insensitive)
    let icon = document.querySelector(`i[iconname="${iconName}"], i[iconname="${iconName.toLowerCase()}"]`);

    // Strategy 2: Try data-icon-name attribute
    if (!icon) {
      icon = document.querySelector(`i[data-icon-name="${iconName}"], i[data-icon-name="${iconName.toLowerCase()}"]`);
    }

    if (!icon) {
      return null;
    }

    // Navigate up the DOM tree to find the clickable parent element
    // OneDrive typically wraps icons in button or div elements with click handlers
    let clickableParent = icon;
    let maxDepth = 5; // Limit upward traversal to avoid going too far

    while (clickableParent && maxDepth > 0) {
      const tagName = clickableParent.tagName.toLowerCase();
      const role = clickableParent.getAttribute('role');

      // Check if this element is likely clickable
      if (
        tagName === 'button' ||
        role === 'button' ||
        clickableParent.onclick ||
        clickableParent.hasAttribute('data-automationid')
      ) {
        return clickableParent;
      }

      clickableParent = clickableParent.parentElement;
      maxDepth--;
    }

    // If no clear clickable parent found, return the icon's immediate parent
    return icon.parentElement;
  }

  /**
   * Check if an element is visible and interactable
   * @param {HTMLElement|null} element - The element to check
   * @returns {boolean} - True if element is visible
   */
  function isElementVisible(element) {
    if (!element) return false;

    const style = window.getComputedStyle(element);
    return style.display !== 'none' &&
           style.visibility !== 'hidden' &&
           style.opacity !== '0' &&
           element.offsetWidth > 0 &&
           element.offsetHeight > 0;
  }

  /**
   * Click a button with retry logic
   * @param {string} iconName - The icon name to search for
   * @param {string} actionName - Human-readable action name for logging
   * @returns {Promise<boolean>} - True if click succeeded, false otherwise
   */
  async function clickButtonWithRetry(iconName, actionName) {
    let retries = 0;
    let hasLoggedWaiting = false;

    return new Promise((resolve) => {
      const attemptClick = () => {
        const button = findButtonByIcon(iconName);

        if (button && isElementVisible(button)) {
          // Success! Click the button
          button.click();
          console.log(`✓ ${actionName} button clicked successfully`);
          resolve(true);
          return;
        }

        retries++;

        if (retries >= MAX_RETRIES) {
          // Max retries reached
          console.log(`✗ ${actionName} buttons not currently visible (tried for ${MAX_RETRY_DURATION_MS}ms)`);
          resolve(false);
          return;
        }

        // Log waiting message only once
        if (!hasLoggedWaiting) {
          console.log(`⏳ Waiting for ${actionName.toLowerCase()} button to become visible...`);
          hasLoggedWaiting = true;
        }

        // Retry after interval
        setTimeout(attemptClick, RETRY_INTERVAL_MS);
      };

      // Start the first attempt
      attemptClick();
    });
  }

  /**
   * Handle keyboard shortcuts
   */
  document.addEventListener('keydown', async (event) => {
    // Only handle Ctrl key combinations (not Meta/Cmd)
    // Use event.ctrlKey specifically to ensure Ctrl works on Mac
    if (!event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) {
      return;
    }

    let handled = false;

    // Ctrl + [ : Accept Revision
    if (event.key === '[') {
      console.log('⌨️  Ctrl+[ pressed - triggering Accept Revision');
      handled = true;
      event.preventDefault();
      await clickButtonWithRetry('AcceptRevision_24', 'Accept Revision');
    }
    // Ctrl + ] : Reject Revision
    else if (event.key === ']') {
      console.log('⌨️  Ctrl+] pressed - triggering Reject Revision');
      handled = true;
      event.preventDefault();
      await clickButtonWithRetry('RejectRevision_24', 'Reject Revision');
    }
    // Ctrl + ' : Previous Revision
    else if (event.key === "'") {
      console.log('⌨️  Ctrl+\' pressed - triggering Previous Revision');
      handled = true;
      event.preventDefault();
      await clickButtonWithRetry('PreviousRevision_24', 'Previous Revision');
    }
    // Ctrl + \ : Next Revision
    else if (event.key === '\\') {
      console.log('⌨️  Ctrl+\\ pressed - triggering Next Revision');
      handled = true;
      event.preventDefault();
      await clickButtonWithRetry('NextRevision_24', 'Next Revision');
    }

    // If we handled a shortcut, also prevent any default browser behavior
    if (handled) {
      event.stopPropagation();
    }
  }, true); // Use capture phase to intercept before other handlers

  // Log keyboard shortcut availability
  console.log(`Keyboard shortcuts active ${frameInfo}:`);
  console.log('  Ctrl+[ → Accept Revision');
  console.log('  Ctrl+] → Reject Revision');
  console.log('  Ctrl+\' → Previous Revision');
  console.log('  Ctrl+\\ → Next Revision');

  // For iframe, log when the document is in focus
  if (isIframe) {
    window.addEventListener('focus', () => {
      console.log('📝 Word editor iframe has focus - shortcuts ready');
    }, { once: true });
  }
})();
