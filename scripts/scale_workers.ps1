param(
    [int]$count = 2
)

# Manual worker scaling via compose (the in-container autoscaler will still
# adjust worker count based on queue depth within its own limits).

docker compose up -d --scale worker=$count
if ($LASTEXITCODE -ne 0) {
    docker-compose up -d --scale worker=$count
}

Write-Host "Requested scaling to $count worker(s)"
