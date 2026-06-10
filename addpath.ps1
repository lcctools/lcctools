$oldPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$newPath = 'D:\lcctools;' + $oldPath
[Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
Write-Host 'Done: D:\lcctools added to user PATH'
