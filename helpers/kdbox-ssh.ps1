# kdbox-ssh.ps1 - run a command on the box over SSH from Windows PowerShell.
# The box runs OpenSSH 6.4, so RSA key + legacy algorithm flags are required.
# Edit $BoxIP, or pass -BoxIP. Put your private key where $KeyPath points.
param(
  [Parameter(Mandatory=$true)][string]$Cmd,
  [string]$BoxIP   = "192.168.1.50",
  [string]$KeyPath = "$env:USERPROFILE\.ssh\kdbox_rsa"
)
ssh -i "$KeyPath" -o StrictHostKeyChecking=no -o UserKnownHostsFile=NUL `
    -o BatchMode=yes -o PubkeyAcceptedKeyTypes=+ssh-rsa -o HostKeyAlgorithms=+ssh-rsa `
    -o ConnectTimeout=10 root@$BoxIP $Cmd
