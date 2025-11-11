# OneDrive Revision Shortcuts - Installation Guide

This Chrome extension adds keyboard shortcuts for OneDrive revision controls.

## Keyboard Shortcuts

- **Ctrl + [** → Accept Revision
- **Ctrl + ]** → Move to Next Revision

## Installation Steps

### 1. Download the Extension

Ensure you have the following files in the `onedrive-shortcuts` folder:
- `manifest.json`
- `content.js`
- `INSTALL.md` (this file)

### 2. Open Chrome Extensions Page

1. Open Google Chrome
2. Navigate to `chrome://extensions/`
3. Alternatively, click the three dots menu (⋮) → More tools → Extensions

### 3. Enable Developer Mode

1. Look for the "Developer mode" toggle in the top-right corner
2. Turn it **ON** (it should turn blue/enabled)

### 4. Load the Extension

1. Click the **"Load unpacked"** button (appears after enabling Developer mode)
2. Navigate to and select the `onedrive-shortcuts` folder
3. Click **"Select Folder"** (or "Open" depending on your OS)

### 5. Verify Installation

You should see the extension appear in your extensions list with:
- Name: "OneDrive Revision Shortcuts"
- Status: Enabled (toggle should be blue)
- A keyboard emoji icon (⌨️)

## Usage

### 1. Open OneDrive

1. Navigate to `https://onedrive.live.com`
2. Open a document with revision tracking (e.g., Word document with tracked changes)

### 2. Use the Shortcuts

When viewing a document with revisions:
- Press **Ctrl + [** to accept the current revision
- Press **Ctrl + ]** to move to the next revision

### 3. Check Console (Optional)

To see debug messages:
1. Right-click on the page → "Inspect" → "Console" tab
2. Look for messages like:
   - "OneDrive Revision Shortcuts extension loaded"
   - "Keyboard shortcuts active"
   - Success/waiting messages when shortcuts are triggered

## Troubleshooting

### Shortcuts Not Working

**Issue**: Pressing Ctrl+[ or Ctrl+] doesn't do anything

**Solutions**:
1. **Check you're on the correct page**: Shortcuts only work on `https://onedrive.live.com/personal/*` URLs
2. **Verify revision buttons exist**: The shortcuts only work when revision controls are visible in the document
3. **Check browser console**: Open Developer Tools (F12) and check for error messages
4. **Reload the page**: Press F5 or Ctrl+R to refresh the page
5. **Verify extension is enabled**: Go to `chrome://extensions/` and ensure the extension toggle is ON

### Extension Not Loading

**Issue**: Extension doesn't appear after loading

**Solutions**:
1. **Check Developer Mode**: Ensure "Developer mode" is enabled in `chrome://extensions/`
2. **Verify folder structure**: Make sure you selected the `onedrive-shortcuts` folder itself, not a parent folder
3. **Check for errors**: Look for error messages on the extension card in `chrome://extensions/`
4. **Reload extension**: Click the refresh icon (🔄) on the extension card

### Buttons Not Found

**Issue**: Console shows "buttons not currently visible"

**Solutions**:
1. **Wait for page to load**: The extension retries for 3 seconds to find buttons
2. **Check document type**: Ensure you're viewing a document with revision tracking enabled
3. **Verify button visibility**: The revision controls must be visible in the UI
4. **Try different document**: Some documents may not have revision controls available

### Conflicts with Other Extensions

**Issue**: Shortcuts work inconsistently or conflict with other extensions

**Solutions**:
1. **Disable conflicting extensions**: Temporarily disable other keyboard shortcut extensions
2. **Check for key binding conflicts**: Some extensions may use the same shortcuts
3. **Test in Incognito mode**: Open Incognito window and enable this extension only

## How It Works

### Button Detection

The extension finds revision buttons using these selectors:
- Primary: `i[iconname="AcceptRevision_24"]` and `i[iconname="NextRevision_24"]`
- Fallback: `i[data-icon-name="AcceptRevision_24"]` and `i[data-icon-name="NextRevision_24"]`

### Retry Logic

If buttons aren't immediately found:
- Retries every **500ms** for up to **3 seconds** (6 attempts)
- Logs "Waiting for revision buttons..." message
- Gracefully fails with helpful message if buttons remain hidden

### Click Simulation

The extension:
1. Finds the icon element
2. Traverses up the DOM to find the clickable parent button
3. Simulates a click on that parent element

## Updating the Extension

If you make changes to the extension files:

1. Go to `chrome://extensions/`
2. Find "OneDrive Revision Shortcuts"
3. Click the refresh icon (🔄) next to the extension
4. Reload any open OneDrive tabs

## Uninstalling

To remove the extension:

1. Go to `chrome://extensions/`
2. Find "OneDrive Revision Shortcuts"
3. Click **"Remove"**
4. Confirm the removal

## Technical Details

- **Manifest Version**: 3 (latest Chrome extension standard)
- **Target Domain**: `https://onedrive.live.com/personal/*`
- **Permissions**: Host permissions for `onedrive.live.com`
- **Key Detection**: Uses `event.ctrlKey` specifically (ensures Ctrl works on Mac)
- **Retry Mechanism**: 500ms intervals, 3-second timeout

## Support

For issues or questions:
1. Check the browser console for error messages (F12 → Console tab)
2. Verify you're on the correct OneDrive URL pattern
3. Ensure revision controls are visible in the document
4. Try reloading the extension and the page

## Privacy

This extension:
- ✓ Only runs on OneDrive pages
- ✓ Does not collect or transmit any data
- ✓ Only interacts with revision control buttons
- ✓ All processing happens locally in your browser

Enjoy faster revision management! ⌨️
