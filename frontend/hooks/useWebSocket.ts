"use client"

import { useEffect, useRef, useState, useCallback } from "react"

type MessageHandler = (data: any) => void

export function useWebSocket(url: string, handlers: Record<string, MessageHandler>) {
  const ws = useRef<WebSocket | null>(null)
  const handlersRef = useRef(handlers)
  const [connected, setConnected] = useState(false)
  const reconnectTimeout = useRef<ReturnType<typeof setTimeout>>()
  const reconnectCount = useRef(0)
  const mounted = useRef(true)

  handlersRef.current = handlers

  const connect = useCallback(() => {
    if (ws.current?.readyState === WebSocket.OPEN || ws.current?.readyState === WebSocket.CONNECTING) return
    try {
      const socket = new WebSocket(url)
      let pingInterval: ReturnType<typeof setInterval>

      socket.onopen = () => {
        if (!mounted.current) { socket.close(); return }
        setConnected(true)
        reconnectCount.current = 0
        pingInterval = setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "ping" }))
        }, 15000)
      }

      socket.onclose = () => {
        clearInterval(pingInterval)
        if (!mounted.current) return
        setConnected(false)
        reconnectCount.current++
        const delay = Math.min(1000 * Math.pow(2, reconnectCount.current), 30000)
        reconnectTimeout.current = setTimeout(connect, delay)
      }

      socket.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)
          const handler = handlersRef.current[msg.type]
          if (handler) handler(msg.data || msg)
        } catch { /* ignore parse errors */ }
      }

      socket.onerror = () => {
        socket.close()
      }

      ws.current = socket
    } catch {
      if (!mounted.current) return
      reconnectCount.current++
      const delay = Math.min(1000 * Math.pow(2, reconnectCount.current), 30000)
      reconnectTimeout.current = setTimeout(connect, delay)
    }
  }, [url])

  useEffect(() => {
    mounted.current = true
    connect()
    return () => {
      mounted.current = false
      clearTimeout(reconnectTimeout.current)
      ws.current?.close()
      ws.current = null
    }
  }, [connect])

  return { connected, reconnectCount: reconnectCount.current, ws: ws.current }
}
