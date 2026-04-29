# WinGet Submission

Chickenwing can become installable with:

```powershell
winget install chickenwing
```

But that only works after the package is accepted into the public WinGet community repository:

- https://github.com/microsoft/winget-pkgs

## Current state

- GitHub release asset exists
- Windows `.exe` build pipeline exists
- WinGet manifests can be generated from the latest release

## Generate manifests

```powershell
py .\scripts\generate-winget-manifests.py
```

That writes manifests here:

```text
packaging/winget/manifests/c/Chyckenwing/Chickenwing/<version>
```

## Next steps to go live in WinGet

1. Fork `microsoft/winget-pkgs`
2. Copy the generated manifest folder into the matching path in that fork
3. Validate the manifest with `winget validate`
4. Open a pull request to `microsoft/winget-pkgs`
5. Wait for package validation and merge

After the pull request is merged and replicated to the public source, users will be able to run:

```powershell
winget install Chyckenwing.Chickenwing
```

Depending on search ranking and package metadata, they may also be able to install with a simpler search term once the package is known to WinGet.
