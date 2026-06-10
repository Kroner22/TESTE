import type { Metadata } from "next"
import { Providers } from "./providers"
import "./globals.css"

export const metadata: Metadata = {
  title: "ScoreSage | Análise Esportiva Inteligente",
  description: "Plataforma de análise esportiva com oportunidades de valor, movimentos de mercado e alertas em tempo real.",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" className="dark">
      <body className="min-h-screen bg-brand-bg antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  )
}
