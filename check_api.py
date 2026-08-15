with open('api_server.py') as f:
    content = f.read()

print('_main_loop global:', '_main_loop = None' in content)
print('startup capture hook:', '_capture_loop' in content)
print('on_event startup:', '@app.on_event("startup")' in content)
print('_broadcast_voice_status def:', 'def _broadcast_voice_status' in content)
print('called from voice_trigger:', '_broadcast_voice_status("listening")' in content)