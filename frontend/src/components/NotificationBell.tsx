import { useCallback, useEffect, useState } from 'react'
import { api, type NotificationList } from '../api'
import { Button } from './ui'

export default function NotificationBell() {
  const [data, setData] = useState<NotificationList>({ unread_count: 0, results: [] })
  const [open, setOpen] = useState(false)

  const load = useCallback(() => {
    api<NotificationList>('/api/notifications/')
      .then(setData)
      .catch(() => undefined)
  }, [])

  useEffect(() => {
    load()
  }, [load])

  async function markRead(id: number) {
    await api(`/api/notifications/${id}/read/`, { method: 'POST' })
    load()
  }

  return (
    <div className="bell">
      <Button
        variant="ghost"
        aria-label={`Notificações (${data.unread_count} não lidas)`}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true" focusable="false">
          <path
            d="M10 2.5a4.5 4.5 0 0 0-4.5 4.5c0 3-1.5 4-1.5 4h12s-1.5-1-1.5-4A4.5 4.5 0 0 0 10 2.5Z"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinejoin="round"
          />
          <path d="M8 14a2 2 0 0 0 4 0" fill="none" stroke="currentColor" strokeWidth="1.8" />
        </svg>
        {data.unread_count > 0 && <span className="bell-count">{data.unread_count}</span>}
      </Button>
      {open && (
        <div className="bell-panel">
          {data.results.length === 0 ? (
            <p>Nenhuma notificação.</p>
          ) : (
            <ul>
              {data.results.map((n) => (
                <li key={n.id} className={n.read ? '' : 'unread'}>
                  <div className="bell-titulo">{n.title}</div>
                  {n.message && <small className="sub">{n.message}</small>}
                  {!n.read && (
                    <div>
                      <Button variant="secondary" onClick={() => markRead(n.id)}>
                        Marcar como lida
                      </Button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
