param(
    [int]$count = 2
)

# Try `docker compose` first, fallback to `docker-compose`
try {
    docker compose up -d --scale worker=$count
} catch {
    docker-compose up -d --scale worker=$count
}

Write-Host "Requested scaling to $count worker(s)"
