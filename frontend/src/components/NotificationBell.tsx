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
        🔔
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
                  <div>{n.title}</div>
                  {n.message && <small>{n.message}</small>}
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
