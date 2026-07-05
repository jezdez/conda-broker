Source demos/_settings.tape

Output demos/provider-plugin.gif
Output demos/provider-plugin.mp4

Hide
Type `eval "$(pixi shell-hook -s bash -e dev)"`
Enter
Wait /\)/
Type `export PS1="$DEMO_PS1" && export CONDA_BROKER_RUNTIME_DIR=/tmp/conda-broker-demo-provider/runtime && export CONDA_BROKER_LOG_DIR=/tmp/conda-broker-demo-provider/logs && rm -rf /tmp/conda-broker-demo-provider`
Enter
Wait /\$/
Type `cb stop >/dev/null 2>&1 || true`
Enter
Wait /\$/
Type "clear"
Enter
Wait /\$/
Show

Type "# A provider exposes conda_broker_services()"
Enter
Sleep 500ms
Type@80ms "sed -n '1,80p' demos/fixtures/demo-provider/demo_provider/broker.py"
Enter
Wait /\$/
Sleep 2s
Hide
Type "clear"
Enter
Wait /\$/
Show

Type "# Install the provider package"
Enter
Sleep 500ms
Type@80ms "python -m pip install -q -e demos/fixtures/demo-provider"
Enter
Wait /\$/
Hide
Type "clear"
Enter
Wait /\$/
Show

Type "# The broker registry discovers its services"
Enter
Sleep 500ms
Type@80ms "cb list"
Enter
Wait /\$/
Sleep 2s
