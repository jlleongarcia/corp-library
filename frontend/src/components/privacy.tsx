import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import api from '../lib/api'
import type { PrivacyInfo } from '../types'

/** Date of the notice's current wording; change it whenever the text changes. */
export const NOTICE_VERSION = { es: '8 de octubre de 2026', en: '8 October 2026' }

export function usePrivacy() {
  return useQuery<PrivacyInfo>({
    queryKey: ['privacy'],
    queryFn: () => api.get('/privacy').then((r) => r.data),
    staleTime: 60 * 60_000,
  })
}

/**
 * A value from .env, or a visible placeholder naming the setting to fill in:
 * the notice must never go live with a blank where the controller should be.
 */
export function Fact({ value, setting }: { value: string | undefined; setting: string }): ReactNode {
  if (value) return value
  return (
    <span className="bg-amber-100 text-amber-900 rounded px-1 font-mono text-[0.85em]">
      [pendiente: {setting}]
    </span>
  )
}

/**
 * First layer of the privacy information (art. 11 LOPDGDD): who, why, on what
 * basis, to whom, and how to exercise rights, with a link to the full notice.
 * Shown at the bottom of every page and on the sign-in page, because data is
 * collected from the first request (with SSO, the user may never see the sign-in page).
 */
export function PrivacyFooter({ className = '' }: { className?: string }) {
  const { data } = usePrivacy()
  return (
    <footer className={`text-[11px] leading-relaxed text-gray-500 ${className}`}>
      <p>
        <strong className="font-semibold text-gray-600">Protección de datos.</strong>{' '}
        Responsable: <Fact value={data?.controller} setting="PRIVACY_CONTROLLER" />.
        Finalidad: identificarle, mostrarle solo los documentos que sus permisos de Windows le permiten abrir y
        registrar su actividad en esta aplicación (inicios de sesión, búsquedas y documentos consultados o
        descargados) para garantizar la seguridad de la información; no se usa para evaluar su rendimiento.
        Legitimación: su relación laboral, las obligaciones legales de seguridad y el interés legítimo de la
        empresa. Destinatarios: no se ceden datos a terceros salvo obligación legal; no salen de la red de la
        empresa. Derechos: acceso, rectificación, supresión, oposición, limitación y portabilidad ante{' '}
        <Fact value={data?.contact} setting="PRIVACY_CONTACT" />, y reclamación ante la AEPD.{' '}
        <Link to="/privacy" className="text-blue-700 hover:underline">Aviso de privacidad completo</Link>
        {' · '}
        <Link to="/privacy?lang=en" className="text-blue-700 hover:underline">Privacy notice (English)</Link>
      </p>
    </footer>
  )
}
