# Common Windows console theme. All colors follow simple roles so Windows
# PowerShell 5.1 and PowerShell 7 both display the interface correctly.
Set-StrictMode -Off

function Show-MorphorumBanner {
    param([string]$Mode = 'MORPHORUM')
    try { $Host.UI.RawUI.WindowTitle = "Morphorum | $Mode" } catch {}
    Write-Host ''
    Write-Host '  __  __  ___  ____  ____  _   _  ___  ____  _   _ __  __' -ForegroundColor Cyan
    Write-Host ' |  \/  |/ _ \|  _ \|  _ \| | | |/ _ \|  _ \| | | |  \/  |' -ForegroundColor Cyan
    Write-Host ' | |\/| | | | | |_) | |_) | |_| | | | | |_) | | | | |\/| |' -ForegroundColor Cyan
    Write-Host ' | |  | | |_| |  _ <|  __/|  _  | |_| |  _ <| |_| | |  | |' -ForegroundColor Cyan
    Write-Host ' |_|  |_|\___/|_| \_\_|   |_| |_|\___/|_| \_\\___/|_|  |_|' -ForegroundColor Cyan
    Write-Host ''
    Write-Host "    LOCAL AI IMAGE + MOTION STUDIO  |  $($Mode.ToUpperInvariant())" -ForegroundColor Magenta
    Write-Host '    -------------------------------------------------------' -ForegroundColor DarkGray
    Write-Host ''
}
function Write-MorphorumSection([string]$Name) {
    Write-Host ''
    Write-Host "  >> $Name" -ForegroundColor Magenta
    Write-Host '  -------------------------------------------------------' -ForegroundColor DarkGray
}
function Step([string]$Text) { Write-Host "  [>] $Text" -ForegroundColor Cyan }
function Okay([string]$Text) { Write-Host "  [+] $Text" -ForegroundColor Green }
function Warn([string]$Text) { Write-Host "  [!] $Text" -ForegroundColor Yellow }
function Fail([string]$Text) { Write-Host "  [X] $Text" -ForegroundColor Red }
function Write-MorphorumDetail([string]$Label, [string]$Value) {
    Write-Host ("  {0,-17}" -f ($Label + ':')) -ForegroundColor DarkGray -NoNewline
    Write-Host $Value -ForegroundColor White
}
function Write-MorphorumNext([string]$Title, [string]$Command) {
    Write-Host ("  {0,-17}" -f ($Title + ':')) -ForegroundColor DarkGray -NoNewline
    Write-Host $Command -ForegroundColor Cyan
}
