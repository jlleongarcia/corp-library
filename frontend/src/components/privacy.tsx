import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import api from '../lib/api'
import type { PrivacyInfo } from '../types'

/** Date of the notice's current wording; change it whenever the text changes (docs/PRIVACY.md). */
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

/** Short name of the supervisory authority: the acronym in brackets, if there is one. */
export function authorityShort(name: string | undefined): string {
  return name?.match(/\(([^)]+)\)\s*$/)?.[1] ?? name ?? 'AEPD'
}

/**
 * First layer of the privacy information (LOPDGDD art. 11) for a Spanish public
 * institution: controller and DPO, purpose, legal basis, recipients, rights, and
 * a link to the full notice. Shown at the bottom of every page and on the sign-in
 * page, because data is collected from the first request (with SSO, the user may
 * never see the sign-in page).
 */
export function PrivacyFooter({ className = '' }: { className?: string }) {
  const { data } = usePrivacy()
  return (
    <footer className={`text-[11px] leading-relaxed text-gray-500 ${className}`}>
      <p>
        <strong className="font-semibold text-gray-600">Protección de datos.</strong>{' '}
        Responsable: <Fact value={data?.controller} setting="PRIVACY_CONTROLLER" />. Delegado de Protección de
        Datos: <Fact value={data?.dpo} setting="PRIVACY_DPO" />. Finalidad: identificarle, mostrarle solo los
        documentos que sus permisos de Windows le permiten abrir y, por seguridad de la información, registrar su
        actividad en esta aplicación (inicios de sesión, búsquedas y documentos consultados o descargados); no se
        usa para evaluar su desempeño. Legitimación: misión de interés público y obligaciones legales de seguridad,
        incluido el Esquema Nacional de Seguridad (art. 6.1.c y e RGPD). Destinatarios: no se comunican datos
        salvo obligación legal; no salen de la red de la institución. Derechos: acceso, rectificación, supresión,
        limitación y oposición ante <Fact value={data?.contact} setting="PRIVACY_CONTACT" />, y reclamación ante
        la autoridad de control ({authorityShort(data?.authority_name)}).{' '}
        <Link to="/privacy" className="text-blue-700 hover:underline">Aviso de privacidad completo</Link>
        {' · '}
        <Link to="/privacy?lang=en" className="text-blue-700 hover:underline">Privacy notice (English)</Link>
      </p>
    </footer>
  )
}
