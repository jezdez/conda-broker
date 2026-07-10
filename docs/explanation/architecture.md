# Architecture

`conda-broker` has five main parts:

1. The conda plugin registers `conda broker` and broker settings lazily.
2. The CLI parses commands and renders Rich or JSON output.
3. `ServiceRegistry` is a pluggy manager that discovers provider hooks and
   stores validated `CondaService` objects.
4. `BrokerServer` owns the user-scoped broker process, IPC server, state,
   and supervisor.
5. `ServiceSupervisor` resolves endpoints, starts, stops, observes,
   restarts, and reports child processes.

Application behavior belongs to those objects rather than module-level helper
collections. `BrokerLease` owns single-instance files and lock lifetime,
`BrokerRequest` owns RPC authentication and normalization, `ManagedProcess`
owns one child lifecycle, and `BrokerConsole` owns all Rich and JSON rendering.
The remaining module-level functions are adapters required by conda hooks,
argparse command dispatch, and Python entry points.

```{mermaid}
flowchart LR
    User["User CLI"] --> CLI["cb / conda broker"]
    Plugin["Provider package"] --> Registry["ServiceRegistry"]
    Registry --> Broker["BrokerServer"]
    CLI --> IPC["Authenticated localhost JSON-RPC"]
    IPC --> Broker
    Broker --> Supervisor["ServiceSupervisor"]
    Supervisor --> Service["Child service process"]
    Supervisor --> Endpoints["Resolved endpoints"]
    Supervisor --> Logs["Service logs"]
    Broker --> Events["events.jsonl"]
```

The broker does not start during arbitrary conda invocations. Lightweight
`Service` queries only ask a running broker and return immediately when it is
absent. Explicit `Broker.status()`, `list_services()`, enable, and disable
operations may discover providers offline because those operations need the
catalog. Startup is reserved for explicit commands and explicit `Broker` API
calls.

Endpoint resolution happens immediately before process launch. Static ports
are reported as-is. Dynamic endpoints get a broker-assigned local port and
environment variables that the child process can read before binding. The
broker reserves all dynamic ports while composing one service launch, then
releases them immediately before creating the child.
