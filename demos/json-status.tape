Source demos/_settings.tape

Output demos/json-status.gif
Output demos/json-status.mp4

Hide
Type `eval "$(pixi shell-hook -s bash -e dev)"`
Enter
Wait /\)/
Type `export PS1="$DEMO_PS1" && export CONDA_BROKER_RUNTIME_DIR=/tmp/conda-broker-demo-json/runtime && export CONDA_BROKER_LOG_DIR=/tmp/conda-broker-demo-json/logs && rm -rf /tmp/conda-broker-demo-json && python -m pip install -q -e demos/fixtures/demo-provider`
Enter
Wait /\$/
Type `cb stop >/dev/null 2>&1 || true`
Enter
Wait /\$/
Type "clear"
Enter
Wait /\$/
Show

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
