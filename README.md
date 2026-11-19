# cyclonedx-maven-plugin and cached "not found" artifacts

## Problem

When `cyclonedx-maven-plugin` runs in a multi-module reactor **before the modules are packaged**
(for example `mvn validate cyclonedx:makeAggregateBom`), it asks the remote repository for a
sibling module's jar. The artifact is not there yet, so the repository answers 404.
Maven then writes a `<artifact>.jar.lastUpdated` marker into the local repository and does not
retry until the update interval has elapsed (daily by default) or `-U` is used.

If the artifact is published to the remote afterwards, builders that share the poisoned local
repository fail with:

```
test:a:jar:1.0 was not found in http://127.0.0.1:8099/ during a previous attempt.
This failure was cached in the local repository and resolution is not reattempted until
the update interval of proxy has elapsed or updates are forced
```

This is why a team ended up using pass-through to a proxy instead of caching on builders.

## Result

Reproduced with every version tested. No fix was seen in this range.

| Plugin version | Requests unbuilt reactor jar from remote | Leaves cached miss |
|----------------|------------------------------------------|--------------------|
| 2.7.3          | yes                                      | yes                |
| 2.7.9          | yes                                      | yes                |
| 2.9.3          | yes                                      | yes                |

Other observations:

- Both `makeAggregateBom` and per-module `makeBom` trigger it.
- A reactor build without the plugin (`validate`, `package`) leaves no `.lastUpdated` file.
- The plugin fetches jars and POMs for all scopes (compile, test, provided, optional).
- 2.9.3 makes fewer requests overall (200 vs 308 for 2.7.3 and 292 for 2.7.9 on `sample`),
  but that is unrelated to the missing-artifact behaviour.
- One 2.7.3 per-module run exited 1 on first try and passed on rerun; the cause was not captured.
- Only the reactor-sibling trigger was tested. Mitigations (running after `package`, `-U`) were not tested.

## Layout

| Path        | Purpose |
|-------------|---------|
| `proxy/proxy.py` | Logging pass-through proxy to Maven Central on `127.0.0.1:8099`. Serves files from `proxy/overlay/` first (used to "publish" `test:a:1.0`). Paths listed in `proxy/hide.txt` return 404. |
| `sample/`   | Single module with compile, provided, test and optional dependencies. Shows which artifacts the plugin requests. |
| `reactor/`  | Parent with modules `a` and `b` (`b` depends on `a`). Reproduces the cached miss. |
| `consumer/` | Project depending on `test:a:1.0`. Proves the cached miss blocks resolution after publishing. |
| `*/settings.xml` | Mirrors everything to the proxy. |

## Reproducing

Requires Maven, a JDK and Python 3. Run from the repository root (Git Bash).

```sh
# 1. start the proxy (log goes to proxy/requests.log)
(cd proxy && python proxy.py 8099 "$PWD/requests.log" &)

# 2. reactor test, per plugin version, with a fresh local repo
cd reactor
for v in 2.7.3 2.7.9 2.9.3; do
  rm -rf ../rrepo-$v
  mvn -B -s settings.xml -Dmaven.repo.local=../rrepo-$v \
      validate org.cyclonedx:cyclonedx-maven-plugin:$v:makeAggregateBom
  find ../rrepo-$v/test -name '*.lastUpdated'     # expect test/a/1.0/a-1.0.jar.lastUpdated
done

# 3. a is now "published" (proxy/overlay/test/a/1.0); resolve it from the poisoned repo
cd ../consumer
cp -r ../rrepo-2.9.3 ../prepo
mvn -B -s settings.xml -Dmaven.repo.local=../prepo dependency:resolve   # fails: cached miss
rm -rf ../prepo
mvn -B -s settings.xml -Dmaven.repo.local=../prepo dependency:resolve   # succeeds: clean repo
```

Note: `proxy/overlay` contains `a-1.0` from the start, so for step 2 to show a 404 the overlay must be
absent while the plugin runs. Move it aside (`mv proxy/overlay proxy/overlay.off`) for step 2 and
restore it before step 3. In the original run the overlay was added after step 2.

`sample/` is run the same way with `makeBom` to compare per-version requests
(`grep -v ' 200$' proxy/requests.log` lists any non-200 responses).
