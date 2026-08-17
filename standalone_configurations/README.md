# Standalone configuration workspace

Use this directory when you want to keep several standalone test or installation
configurations in the repository checkout without adding them to Git:

```bash
python -m eltako_standalone --config standalone_configurations/local serve
```

The `local/` directory is ignored by Git. It can contain `configuration.yaml`,
`.storage/`, logs and the named profiles managed by the Standalone **Configurations**
page. Do not put real gateway addresses, device ids or credentials into tracked files.

On the Standalone **Configurations** page, **Save current YAML as...** stores a readable
`<name>.yaml` file directly in the selected storage folder. The **Load** button next to a
saved file replaces the active `configuration.yaml` and restarts the runtime. The **View details**
button shows the plain YAML and its summary; **Save as** creates another copy of the active YAML.
The **Delete** button removes a saved YAML or named profile after confirmation; the active
`configuration.yaml` cannot be deleted.
Loading is a replacement operation: persisted UI-created gateways and devices from the previous
configuration are removed before the new configuration is started.

The committed files in `examples/` are safe starting points. Copy one into `local/` and
adapt it to the installation:

```bash
cp standalone_configurations/examples/minimal.yaml \
   standalone_configurations/local/configuration.yaml
```

The existing root-level [`ha.yaml`](../ha.yaml) remains the example used by the development
container. The standalone examples below use the same `eltako:` configuration format.

Each YAML configuration may contain a top-level `description` field. It is metadata for the
standalone configuration browser and is shown together with a summary of the configured gateways,
devices and platforms; it does not affect the Eltako runtime.

The **Choose folder...** button uses the browser's native directory API. The browser manages the
selected folder directly; loading sends a selected YAML to the standalone runtime. In a headless
or unsupported browser setup, enter the server-side path manually instead.
