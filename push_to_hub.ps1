$ErrorActionPreference = "Stop"

Write-Host "1. Building Docker Image..." -ForegroundColor Cyan
docker build --no-cache -t crisocean/lumina:latest .
if ($LASTEXITCODE -ne 0) { Write-Error "Build failed"; exit 1 }

Write-Host "2. Pushing to Docker Hub..." -ForegroundColor Cyan
try {
    docker push crisocean/lumina:latest
}
catch {
    Write-Warning "Push failed!"
    Write-Host "It looks like you aren't logged in or don't have permission." -ForegroundColor Yellow
    Write-Host "Please run 'docker login' in your terminal, enter your Docker Hub credentials, and try again." -ForegroundColor Yellow
    exit 1
}

if ($LASTEXITCODE -ne 0) { 
    Write-Warning "Push failed with exit code $LASTEXITCODE"
    Write-Host "Please check:" -ForegroundColor Yellow
    Write-Host "  1. You are logged in (run 'docker login')" -ForegroundColor Yellow
    Write-Host "  2. You created the repository 'lumina' in Docker Hub (if it doesn't exist)" -ForegroundColor Yellow
    exit 1 
}

Write-Host "Done! Image pushed to crisocean/lumina:latest" -ForegroundColor Green
