Source demos/_settings.tape

Output demos/logs-events.gif
Output demos/logs-events.mp4

Hide
Type `eval "$(pixi shell-hook -s bash -e dev)"`
Enter
Wait /\)/
Type `export PS1="$DEMO_PS1" && export CONDA_BROKER_RUNTIME_DIR=/tmp/conda-broker-demo-logs/runtime && export CONDA_BROKER_LOG_DIR=/tmp/conda-broker-demo-logs/logs && rm -rf /tmp/conda-broker-demo-logs && python -m pip install -q -e demos/fixtures/demo-provider`
Enter
Wait /\$/
Type `cb stop >/dev/null 2>&1 || true`
Enter
Wait /\$/
Type "clear"
Enter
Wait /\$/
Show

Type "# Start a service that writes logs"
Enter
Sleep 500ms
Type@80ms "cb start heartbeat"
Enter
Wait /\$/
Sleep 2s
Hide
Type "clear"
Enter
Wait /\$/
Show

Type "# Read the service log"
Enter
Sleep 500ms
Type@80ms "cb logs heartbeat --lines 5"
Enter
Wait /\$/
Sleep 1s
Hide
Type "clear"
Enter
Wait /\$/
Show

Type "# Emit a provider event"
Enter
Sleep 500ms
Type@80ms `python -c 'from conda_broker.client import emit_event; emit_event("demo.note", service="heartbeat", message="operator checked logs")'`
Enter
Wait /\$/
Hide
Type "clear"
Enter
Wait /\$/
Show

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
