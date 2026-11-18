# Atalhos do terminal da operadora para a demo ao vivo.
# Uso, na raiz do checkout (PowerShell 7 ou Windows PowerShell 5.1):
#   . .\docs\speaker\demo-terminal.ps1 -Directory "artifacts/private/demo-24nov"
# Os atalhos só leem propostas e chamam a revisão local. A atestação continua
# manual: `aprovar` mostra o resumo, copia "ATESTO <hash>" e espera você colar.

param([Parameter(Mandatory = $true)][string]$Directory)

if (-not (Test-Path -LiteralPath (Join-Path $Directory "demo.json"))) {
    throw "Atendimento não encontrado em '$Directory'. Rode este script na raiz do checkout."
}
$global:DonaMariaDirectory = $Directory
# Saída UTF-8 do Python lida corretamente no console (acentos e JSON).
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

function dm {
    uv run --locked --no-sync python -X utf8 -m dona_maria.onboarding review --directory $global:DonaMariaDirectory @args
}

function ConvertTo-DmInstante($value) {
    if ($value -is [string]) { return [DateTimeOffset]::Parse($value) }
    return [DateTimeOffset]$value
}

function Get-DmPropostas {
    $texto = (dm list) -join "`n"
    if (-not $texto.Trim()) { return @() }
    # Atribuir antes do pipeline: no Windows PowerShell 5.1 o array chegaria inteiro.
    $dados = ConvertFrom-Json -InputObject $texto
    return @($dados | Sort-Object { ConvertTo-DmInstante $_.created_at })
}

function Get-DmPendentes {
    $agora = [DateTimeOffset]::UtcNow
    return @(Get-DmPropostas | Where-Object {
            $_.status -eq "PENDING" -and (ConvertTo-DmInstante $_.expires_at) -gt $agora
        })
}

function Format-DmResumo($proposta) {
    $payload = $proposta.command.payload
    switch ($proposta.command.kind) {
        "register_recipe_candidate" {
            $receita = $payload.candidate
            if ($receita.changes) { $receita = $receita.changes }
            $linhas = @("Receita: $($receita.title)")
            foreach ($item in @($receita.ingredients)) {
                if ($item) {
                    $linhas += "  - $($item.description): $($item.quantity.value) $($item.quantity.unit) ($($item.preparation_basis))"
                }
            }
            if ($receita.yield_per_batch) { $linhas += "  Rendimento: $($receita.yield_per_batch.servings_per_batch) $($receita.yield_per_batch.sale_unit_label)(s) por lote" }
            $categorias = @($receita.category_reviews | ForEach-Object { $_.category }) -join ", "
            $linhas += "  Categorias revisadas: " + $(if ($categorias) { $categorias } else { "nenhuma" })
            $lacunas = @($receita.declared_gaps).Count
            $linhas += "  Lacunas declaradas: $lacunas"
            return $linhas -join "`n"
        }
        "record_kitchen_facts" {
            $linhas = @("Fatos da cozinha:")
            foreach ($fato in @($payload.facts)) { $linhas += "  - $($fato.category) / $($fato.key) = $($fato.value) $($fato.unit)" }
            return $linhas -join "`n"
        }
        "record_recipe_feedback" { return "Interesse na receita: $($payload.feedback)" }
        "set_production_plan" {
            $linhas = @("Plano de produção:")
            foreach ($item in @($payload.items)) { $linhas += "  - $($item.batches) lote(s), $($item.requested_servings) porção(ões) pedidas" }
            return $linhas -join "`n"
        }
        "accept_recipe" { return "Aceite do prato, vinculado à avaliação atual" }
        "save_menu_decision" {
            if ($payload.scenario_id) { return "Escolha do preço: cenário $($payload.scenario_id)" }
            return "Escolha do preço: R$ $($payload.custom_price)"
        }
        default { return "$($proposta.command.kind): " + ($payload | ConvertTo-Json -Depth 6 -Compress) }
    }
}

function pend {
    $lista = Get-DmPendentes
    if ($lista.Count -eq 0) { Write-Host "Nenhuma proposta pendente válida."; return }
    $agora = [DateTimeOffset]::UtcNow
    for ($i = 0; $i -lt $lista.Count; $i++) {
        $p = $lista[$i]
        $minutos = [math]::Floor(((ConvertTo-DmInstante $p.expires_at) - $agora).TotalMinutes)
        Write-Host ("[{0}] {1} · expira em {2} min" -f ($i + 1), $p.command.kind, $minutos) -ForegroundColor Yellow
        Write-Host (Format-DmResumo $p)
    }
    if ($lista.Count -gt 1) { Write-Host "Há $($lista.Count) propostas. Aprove uma com: aprovar <número>" -ForegroundColor Cyan }
}

function ver([int]$Numero = 1) {
    $lista = Get-DmPendentes
    if ($lista.Count -lt $Numero -or $Numero -lt 1) { Write-Host "Proposta $Numero não está pendente."; return }
    dm inspect $lista[$Numero - 1].id
}

function historico {
    foreach ($p in Get-DmPropostas) {
        $cor = if ($p.status -eq "APPROVED") { "Green" } elseif ($p.status -eq "PENDING") { "Yellow" } else { "DarkGray" }
        Write-Host ("{0,-9} {1}" -f $p.status, $p.command.kind) -ForegroundColor $cor
    }
}

function aprovar([int]$Numero = 0) {
    $lista = Get-DmPendentes
    if ($lista.Count -eq 0) { Write-Host "Nenhuma proposta pendente válida. Peça ao Hermes que refaça a proposta."; return }
    if ($Numero -eq 0) {
        if ($lista.Count -gt 1) { pend; return }
        $Numero = 1
    }
    if ($Numero -lt 1 -or $Numero -gt $lista.Count) { Write-Host "Use um número da lista de pend."; return }
    $p = $lista[$Numero - 1]
    Write-Host "Confira se corresponde ao que a Dona Maria disse:" -ForegroundColor Cyan
    Write-Host (Format-DmResumo $p)
    Set-Clipboard -Value ("ATESTO " + $p.hash)
    Write-Host "Copiei 'ATESTO <hash>'. Se estiver correto, cole (Ctrl+V) e tecle Enter. Para desistir, Ctrl+C." -ForegroundColor Cyan
    $saida = dm approve $p.id --hash $p.hash
    $json = @($saida | Where-Object { $_ -match '^\s*\{' }) | Select-Object -Last 1
    if ($json) {
        $resultado = $json | ConvertFrom-Json
        if ($resultado.ok) {
            Write-Host "Aprovada: $($p.command.kind) · revisão $($resultado.revision)" -ForegroundColor Green
            return
        }
    }
    Write-Host "Não aplicada. Se apareceu AUTHORIZATION_EXPIRED ou STALE_REVISION, peça ao Hermes: 'refaça só essa proposta'. A pasta continua íntegra." -ForegroundColor Red
}

Write-Host "Atalhos carregados para $Directory : pend, aprovar [n], ver [n], historico, dm" -ForegroundColor Green
