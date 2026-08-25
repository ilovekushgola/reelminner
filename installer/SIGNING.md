# Signing notes

The `Reelminner-Setup.exe` produced by this installer is **unsigned**.
Windows SmartScreen will warn users ("Windows protected your PC") until the
installer is code-signed.

## What to do before public distribution

1. Obtain a code-signing certificate (EV certs remove SmartScreen friction
   fastest; OV certs are cheaper and also work).
2. Sign the **Setup exe** with `signtool` (Windows SDK):

   ```powershell
   signtool sign /fd SHA256 /a /tr http://timestamp.digicert.com /td SHA256 /f mycert.pfx /p <password> dist\Reelminner-Setup.exe
   ```

3. Sign the **app exe** too (defeats SmartScreen for the app itself):

   ```powershell
   signtool sign /fd SHA256 /a /tr http://timestamp.digicert.com /td SHA256 /f mycert.pfx /p <password> dist\Reelminner.exe
   ```

4. Verify:

   ```powershell
   signtool verify /pa dist\Reelminner-Setup.exe
   ```

5. (Optional) Submit the signed file to Microsoft SmartScreen for reputation:
   https://www.microsoft.com/en-us/wdsi/filesubmission

## Reproducible builds

`build_exe.py` + `install.bat` are deterministic given the same source tree
and dependency versions. Pin versions in `requirements.txt` if you need
byte-reproducible artifacts.
