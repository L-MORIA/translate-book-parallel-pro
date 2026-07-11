# Create desktop shortcut for translate-book-parallel-pro
$WS = New-Object -ComObject WScript.Shell
$s = $WS.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\translate-book-parallel-pro.lnk')
$s.TargetPath = 'F:\translate-book-parallel-pro\scripts\translate-launcher.bat'
$s.WorkingDirectory = 'F:\translate-book-parallel-pro'
$s.IconLocation = 'F:\translate-book-parallel-pro\assets\translate.ico,0'
$s.Description = 'Translate books via AI (Hermes) - EPUB/PDF/DOCX/TXT'
$s.Save()
Write-Host "✅ Shortcut created: $($s.FullName)"
