Source demos/_settings.tape

Output demos/quickstart.gif

Type "# Discover broker services"
Enter
Sleep 500ms
Type@80ms "cb list"
Enter
Wait /\$/
Sleep 1s

Type "# Enable a service for broker startup"
Enter
Sleep 500ms
Type@80ms "cb enable heartbeat"
Enter
Wait /\$/
Sleep 1s

Type "# Start the service and wait for readiness"
Enter
Sleep 500ms
Type@80ms "cb wait heartbeat --start --timeout 10"
Enter
Wait /\$/
Sleep 1s

Type "# Read recent logs"
Enter
Sleep 500ms
Type@80ms "cb logs heartbeat --lines 3"
Enter
Wait /\$/
Sleep 1s

Type "# Stop the broker"
Enter
Sleep 500ms
Type@80ms "cb stop"
Enter
Wait /\$/
Sleep 1s
