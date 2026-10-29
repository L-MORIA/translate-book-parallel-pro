# Create desktop shortcut for translate-book-parallel-pro
$WS = New-Object -ComObject WScript.Shell
$s = $WS.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\translate-book-parallel-pro.lnk')
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
$s.TargetPath = Join-Path $ScriptDir 'translate-launcher.bat'
$s.WorkingDirectory = $ProjectDir
$s.IconLocation = Join-Path $ProjectDir 'assets\translate.ico,0'
$s.Description = 'Translate books via AI (Hermes) - EPUB/PDF/DOCX'
$s.Save()
# Unicode escape sequences of that form need PowerShell 6+; .ps1 files are
# usually run by 5.1, which would print them literally.
Write-Host "$([char]::ConvertFromUtf32(0x2705)) Shortcut created: $($s.FullName)"
