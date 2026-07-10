Source demos/_settings.tape

Output demos/json-status.gif

Type "# Start a service and ask for JSON"
Enter
Sleep 500ms
Type@80ms "cb start heartbeat"
Enter
Wait /\$/
Sleep 1s

Type "# Broker status as JSON"
Enter
Sleep 500ms
Type@80ms "cb status --json"
Enter
Wait /\$/
Sleep 2s

Type "# Query one service"
Enter
Sleep 500ms
Type@80ms "cb status heartbeat --json"
Enter
Wait /\$/
Sleep 2s

Hide
Type "cb stop"
Enter
Wait /\$/
