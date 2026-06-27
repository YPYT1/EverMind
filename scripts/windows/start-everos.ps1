param(
  [string]$EverOSRepo = "",
  [string]$EverOSRoot = "D:\EverMindMemory\everos",
  [string]$HostName = "127.0.0.1",
  [int]$Port = 3378
)

$ErrorActionPreference = "Stop"

if ($EverOSRepo) {
  uv run --directory $EverOSRepo everos server start --host $HostName --port $Port --root $EverOSRoot
} else {
  everos server start --host $HostName --port $Port --root $EverOSRoot
}

