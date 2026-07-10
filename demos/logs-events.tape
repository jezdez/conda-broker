Source demos/_settings.tape

Output demos/logs-events.gif

Type "# Start a service that writes logs"
Enter
Sleep 500ms
Type@80ms "cb wait heartbeat --start --timeout 10"
Enter
Wait /\$/
Sleep 2s

Type "# Read the service log"
Enter
Sleep 500ms
Type@80ms "cb logs heartbeat --lines 5"
Enter
Wait /\$/
Sleep 1s

Type "# Emit a provider event"
Enter
Sleep 500ms
Type@80ms `python -c 'from conda_broker import Broker; Broker.current().service("heartbeat").emit_event("demo.note", message="operator checked logs")'`
Enter
Wait /\$/

Type "# Inspect recent events"
Enter
Sleep 500ms
Type@80ms "cb events --lines 8"
Enter
Wait /\$/
Sleep 2s

Hide
Type "cb stop"
Enter
Wait /\$/
