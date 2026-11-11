export type HealthResponse = {
  status: 'ok'
  service: 'scholarship-hunter-ai'
}

export async function getHealth(signal: AbortSignal): Promise<HealthResponse> {
  const response = await fetch('/api/health', {
    headers: { Accept: 'application/json' },
    signal: AbortSignal.any([signal, AbortSignal.timeout(5000)]),
  })

  if (!response.ok) {
    throw new Error(`Health check failed: HTTP ${response.status}`)
  }

  const data: unknown = await response.json()
  if (
    typeof data !== 'object' ||
    data === null ||
    !('status' in data) ||
    data.status !== 'ok' ||
    !('service' in data) ||
    data.service !== 'scholarship-hunter-ai'
  ) {
    throw new Error('Unexpected health response')
  }

  return { status: data.status, service: data.service }
}
