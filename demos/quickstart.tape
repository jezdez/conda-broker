Source demos/_settings.tape

Output demos/quickstart.gif
Output demos/quickstart.mp4

Hide
Type `eval "$(pixi shell-hook -s bash -e dev)"`
Enter
Wait /\)/
Type `export PS1="$DEMO_PS1" && export CONDA_BROKER_RUNTIME_DIR=/tmp/conda-broker-demo-quickstart/runtime && export CONDA_BROKER_LOG_DIR=/tmp/conda-broker-demo-quickstart/logs && rm -rf /tmp/conda-broker-demo-quickstart && python -m pip install -q -e demos/fixtures/demo-provider`
Enter
Wait /\$/
Type `cb stop >/dev/null 2>&1 || true`
Enter
Wait /\$/
Type "clear"
Enter
Wait /\$/
Show

Type "# Discover broker services"
Enter
Sleep 500ms
Type@80ms "cb list"
Enter
Wait /\$/
Sleep 1s
Hide
Type "clear"
Enter
Wait /\$/
Show

Type "# Enable and start a service"
Enter
Sleep 500ms
Type@80ms "cb enable heartbeat --start"
Enter
Wait /\$/
Sleep 1s
Hide
Type "clear"
Enter
Wait /\$/
Show

Type "# Inspect service readiness"
Enter
Sleep 500ms
Type@80ms "cb status heartbeat"
Enter
Wait /\$/
Sleep 1s
Hide
Type "clear"
Enter
Wait /\$/
Show

Type "# Read recent logs"
Enter
Sleep 500ms
Type@80ms "cb logs heartbeat --lines 3"
Enter
Wait /\$/
Sleep 1s
Hide
Type "clear"
Enter
Wait /\$/
Show

Type "# Stop the broker"
Enter
Sleep 500ms
Type@80ms "cb stop"
Enter
Wait /\$/
Sleep 1s
