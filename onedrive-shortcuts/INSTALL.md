# OneDrive Revision Shortcuts - Installation Guide

This Chrome extension adds keyboard shortcuts for OneDrive revision controls.

## Keyboard Shortcuts

- **Ctrl + [** → Accept Revision
- **Ctrl + ]** → Reject Revision
- **Ctrl + '** → Previous Revision
- **Ctrl + \\** → Next Revision

## Installation Steps

### 1. Download the Extension

Ensure you have the following files in the `onedrive-shortcuts` folder (download them as zip using the 'Code' button [here](https://github.com/alejoacelas/claude-experiments/edit/claude/onedrive-revision-shortcuts-011CV2DaQ5ZJ7Lb1iT5AZZQP)):
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
3. **Important**: Click inside the document editor to ensure it has focus

### 2. Use the Shortcuts

When viewing a document with revisions:
- Press **Ctrl + [** to accept the current revision
- Press **Ctrl + ]** to reject the current revision
- Press **Ctrl + '** to move to the previous revision
- Press **Ctrl + \** to move to the next revision

**Note**: The shortcuts work inside the Word Online editor, which loads in an iframe at `*.officeapps.live.com`

### 3. Check Console (Optional)

To see debug messages:
1. Right-click on the page → "Inspect" → "Console" tab
2. Look for messages like:
   - "OneDrive Revision Shortcuts extension loaded [iframe: ...]"
   - "Keyboard shortcuts active [iframe: ...]"
   - "Word editor iframe has focus - shortcuts ready"
   - Success/waiting messages when shortcuts are triggered

## Troubleshooting

### Shortcuts Not Working

**Issue**: Pressing keyboard shortcuts doesn't do anything

**Solutions**:
1. **Click inside the document editor**: The Word Online editor is in an iframe, so you need to click inside the document to give it focus
2. **Verify revision buttons exist**: The shortcuts only work when revision controls are visible in the document
3. **Check browser console**: Open Developer Tools (F12) and check for messages:
   - Look for "OneDrive Revision Shortcuts extension loaded [iframe: word-edit.officeapps.live.com]"
   - If you only see "[main page]", the iframe version isn't loading
4. **Reload the extension**: Go to `chrome://extensions/`, find the extension, and click the refresh icon (🔄)
5. **Reload the document**: Press F5 or Ctrl+R to refresh the page after reloading the extension
6. **Verify extension is enabled**: Go to `chrome://extensions/` and ensure the extension toggle is ON

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

### Cross-Frame Support

OneDrive Word Online loads the document editor in an iframe at `*.officeapps.live.com`. The extension:
- Runs on both the main OneDrive page and inside the Word Online iframe
- Uses `"all_frames": true` in the manifest to inject into all frames
- Detects which frame it's running in and logs accordingly
- Keyboard events are captured in the iframe where the editor lives

### Button Detection

The extension finds revision buttons using these selectors:
- Primary: `i[iconname="AcceptRevision_24"]`, `i[iconname="RejectRevision_24"]`, `i[iconname="PreviousRevision_24"]`, and `i[iconname="NextRevision_24"]`
- Fallback: `i[data-icon-name="AcceptRevision_24"]`, `i[data-icon-name="RejectRevision_24"]`, `i[data-icon-name="PreviousRevision_24"]`, and `i[data-icon-name="NextRevision_24"]`

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
- **Target Domains**:
  - `https://onedrive.live.com/personal/*` (main OneDrive page)
  - `https://*.officeapps.live.com/*` (Word Online iframe)
- **Permissions**: Host permissions for `onedrive.live.com` and `*.officeapps.live.com`
- **Frame Injection**: Uses `"all_frames": true` to run in all iframes
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
