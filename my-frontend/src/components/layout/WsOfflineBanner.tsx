"use client";

import { useEffect, useRef, useState } from "react";
import SystemStatusLink from "@/components/navigation/SystemStatusLink";
import { useMarketWebSocketContext } from "@/context/MarketWebSocketProvider";

/** 연결됐다가 끊긴 상태가 이 시간 이상 이어질 때만 안내 */
const OFFLINE_GRACE_MS = 8000;

/**
 * WS 끊김 시 상단 안내 (자동 재연결).
 * 사이트를 새로 열거나 새로고침할 때는 첫 연결이 늦어도(무료 서버 깨우는 중 등) 띄우지 않고,
 * 한 번 연결됐다가 실제로 끊긴 경우에만 표시합니다.
 */
export default function WsOfflineBanner() {
  const ctx = useMarketWebSocketContext();
  const connected = ctx?.isConnected ?? false;
  const everConnected = useRef(false);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (connected) {
      everConnected.current = true;
      setVisible(false);
      return;
    }
    if (!everConnected.current) return;
    const t = window.setTimeout(() => setVisible(true), OFFLINE_GRACE_MS);
    return () => window.clearTimeout(t);
  }, [connected]);

  if (!visible || connected) return null;

  return (
    <div className="ws-offline-banner" role="status">
      <div className="container ws-offline-banner-inner">
        <span>실시간 연결이 잠시 끊겼습니다. 시세는 주기적으로 갱신되며, 자동으로 다시 연결합니다.</span>
        <SystemStatusLink>연결 상태</SystemStatusLink>
      </div>
    </div>
  );
}
