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

The broker does not start during arbitrary conda invocations. Query methods
can read state and ask a running broker for status, but startup is reserved
for explicit commands and explicit `Broker` API calls.

Endpoint resolution happens immediately before process launch. Static ports
are reported as-is. Dynamic endpoints get a broker-assigned local port and
environment variables that the child process can read before binding.
