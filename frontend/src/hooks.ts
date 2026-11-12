import { useEffect, useState, useSyncExternalStore } from 'react'

function subscribeToHash(callback: () => void) {
  window.addEventListener('hashchange', callback)
  return () => window.removeEventListener('hashchange', callback)
}

export function useHashRoute() {
  return useSyncExternalStore(
    subscribeToHash,
    () => window.location.hash || '#/',
    () => '#/',
  )
}

type Resource<T> =
  | { status: 'loading' }
  | { status: 'ready'; data: T }
  | { status: 'error'; message: string }

export function useResource<T>(
  key: string,
  loader: (signal: AbortSignal) => Promise<T>,
) {
  const [revision, setRevision] = useState(0)
  const requestKey = `${key}@${revision}`
  const [result, setResult] = useState<{ key: string; value: Resource<T> }>({
    key: requestKey,
    value: { status: 'loading' },
  })

  useEffect(() => {
    const controller = new AbortController()
    loader(controller.signal).then(
      (data) => {
        if (!controller.signal.aborted)
          setResult({ key: requestKey, value: { status: 'ready', data } })
      },
      (error) => {
        if (!controller.signal.aborted)
          setResult({
            key: requestKey,
            value: {
              status: 'error',
              message:
                error instanceof Error
                  ? error.message
                  : 'Something went wrong. Please try again.',
            },
          })
      },
    )
    return () => controller.abort()
  }, [loader, requestKey])

  return {
    resource:
      result.key === requestKey
        ? result.value
        : ({ status: 'loading' } as Resource<T>),
    retry: () => setRevision((previous) => previous + 1),
  }
}
