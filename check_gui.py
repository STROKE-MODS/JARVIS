with open('gui/index.html') as f:
    content = f.read()

print('overlay div:', 'listening-overlay' in content)
print('voice_status handler:', "d.type === 'voice_status'" in content)
print('showListeningOverlay fn:', 'function showListeningOverlay' in content)
print('hideListeningOverlay fn:', 'function hideListeningOverlay' in content)
print('mic-btn or keyboard-toggle wired:', 'triggerVoiceListen' in content)