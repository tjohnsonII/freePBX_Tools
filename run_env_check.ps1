$ipList = Get-Content "server_ips.txt"
$script = "env_check.sh"
$remotePath = "/home/123net/env_check.sh"
$user = "root"  # Change if needed

foreach ($ip in $ipList) {
    Write-Host "Processing $ip..."
    $dest = $user + "@" + $ip + ":" + $remotePath
    scp $script $dest
    ssh ($user + "@" + $ip) "bash $remotePath" | Out-File -Encoding UTF8 ("env_check_" + $ip + ".txt")
}