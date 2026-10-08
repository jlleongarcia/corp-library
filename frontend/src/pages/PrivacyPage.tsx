import type { ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowLeft, ShieldCheck } from 'lucide-react'
import { Fact, NOTICE_VERSION, usePrivacy } from '../components/privacy'
import type { PrivacyInfo } from '../types'
import { Loading } from './admin/common'

/*
 * Full privacy notice (second layer) for the staff of a Spanish public
 * institution: GDPR arts. 13 and 14, LOPDGDD art. 11. Why it exists and why it
 * says what it says: docs/PRIVACY.md. Spanish is the authoritative text; the
 * English one is a translation. Every fact about the app (what is logged,
 * retention, who can read it) is something the code does: change both together,
 * and NOTICE_VERSION with them. Facts about the institution come from .env.
 */

type Lang = 'es' | 'en'

function Section({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="text-base font-semibold text-gray-900">{n}. {title}</h2>
      <div className="space-y-2 text-sm text-gray-700 leading-relaxed">{children}</div>
    </section>
  )
}

function Basis({ head, rows }: { head: [string, string]; rows: [ReactNode, ReactNode][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border border-gray-200 rounded-lg">
        <thead className="bg-gray-50 text-left">
          <tr><th className="p-2.5 font-semibold">{head[0]}</th><th className="p-2.5 font-semibold">{head[1]}</th></tr>
        </thead>
        <tbody className="divide-y divide-gray-200">
          {rows.map(([purpose, basis], i) => (
            <tr key={i} className="align-top">
              <td className="p-2.5 w-1/2">{purpose}</td>
              <td className="p-2.5 w-1/2 bg-gray-50">{basis}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ExternalLink({ href, children }: { href: string; children: ReactNode }) {
  return <a className="text-blue-700 hover:underline break-all" href={href} rel="noopener noreferrer" target="_blank">{children}</a>
}

function RecordLink({ p }: { p: PrivacyInfo }) {
  return p.record_url ? <ExternalLink href={p.record_url}>{p.record_url}</ExternalLink> : <Fact value="" setting="PRIVACY_RECORD_URL" />
}

function Authority({ p }: { p: PrivacyInfo }) {
  return <>{p.authority_name} (<ExternalLink href={p.authority_url}>{p.authority_url.replace(/^https?:\/\//, '')}</ExternalLink>)</>
}

function days(n: number, lang: Lang) {
  return lang === 'es' ? `${n} día${n === 1 ? '' : 's'}` : `${n} day${n === 1 ? '' : 's'}`
}

function NoticeEs({ p }: { p: PrivacyInfo }) {
  const contact = <Fact value={p.contact} setting="PRIVACY_CONTACT" />
  const audit = p.audit_retention_days
  return (
    <>
      <Section n={1} title="¿Quién es el responsable del tratamiento?">
        <p>
          <Fact value={p.controller} setting="PRIVACY_CONTROLLER" />, con NIF{' '}
          <Fact value={p.controller_id} setting="PRIVACY_CONTROLLER_ID" /> y sede en{' '}
          <Fact value={p.controller_address} setting="PRIVACY_CONTROLLER_ADDRESS" />.
          Contacto para cualquier cuestión sobre protección de datos: {contact}.
        </p>
        <p>Delegado de Protección de Datos: <Fact value={p.dpo} setting="PRIVACY_DPO" />.</p>
      </Section>

      <Section n={2} title="¿Qué es Corp Library y qué datos suyos trata?">
        <p>
          Corp Library es una herramienta interna, de solo lectura, para buscar y consultar los documentos de las
          carpetas compartidas del departamento. No crea, modifica ni borra documentos, y cada persona solo ve lo
          que ya puede abrir con sus permisos de Windows. Para funcionar trata los siguientes datos sobre usted:
        </p>
        <ul className="list-disc pl-5 space-y-1">
          <li>
            <strong>Identificación y cuenta:</strong> nombre de usuario de Windows, nombre completo, correo
            electrónico corporativo, identificador de seguridad (SID) de su cuenta y grupos del Directorio Activo
            a los que pertenece.
          </li>
          <li>
            <strong>Sesión:</strong> fecha y hora de inicio de sesión y de última actividad, método de acceso
            (inicio de sesión de Windows o formulario), dirección IP del equipo y tipo de navegador.
          </li>
          <li>
            <strong>Registro de actividad:</strong> inicios de sesión (también los fallidos) y cierres de sesión;
            las búsquedas que realiza, con las palabras buscadas y los filtros aplicados; los documentos que
            consulta, previsualiza o descarga, con su ruta; y los intentos de abrir documentos que el servidor de
            archivos le deniega.
          </li>
        </ul>
        <p>
          <strong>Origen:</strong> los datos de identificación y cuenta proceden del Directorio Activo de la
          institución; los de sesión y actividad se generan al usar la aplicación. Su contraseña no se almacena: se
          comprueba directamente contra el Directorio Activo.
        </p>
        <p>
          No solicitamos categorías especiales de datos (art. 9 RGPD). Como las búsquedas quedan registradas, le
          rogamos que no escriba en el buscador datos personales que no sean necesarios (por ejemplo, datos de
          salud de otra persona).
        </p>
      </Section>

      <Section n={3} title="¿Para qué tratamos sus datos y con qué base jurídica?">
        <Basis head={['Finalidad', 'Base jurídica']} rows={[
          [
            'Identificarle y aplicar sus permisos, para mostrarle únicamente los documentos que puede abrir.',
            'Cumplimiento de una misión realizada en interés público o en el ejercicio de poderes públicos: la ' +
            'gestión de la documentación de la institución por su personal (art. 6.1.e RGPD). Para el personal ' +
            'laboral, además, la ejecución de su contrato de trabajo (art. 6.1.b RGPD).',
          ],
          [
            'Garantizar la seguridad de la información mediante el registro de actividad: detectar, investigar y ' +
            'documentar accesos indebidos, incidentes y violaciones de seguridad de los datos personales que ' +
            'contienen los documentos.',
            'Cumplimiento de obligaciones legales (art. 6.1.c RGPD): art. 32 RGPD, disposición adicional primera ' +
            'de la LOPDGDD y Esquema Nacional de Seguridad (Real Decreto 311/2022), que exige registrar la ' +
            'actividad de los usuarios de los sistemas de información del sector público.',
          ],
          [
            'Mejorar el servicio con estadísticas agregadas (por ejemplo, búsquedas que no obtienen resultados), ' +
            'sin identificar a ninguna persona.',
            'Misión realizada en interés público: la mejora de los servicios de la institución (art. 6.1.e RGPD).',
          ],
        ]} />
        <p>
          <strong>Por qué es necesario el registro de actividad.</strong> La aplicación abre los ficheros con una
          cuenta técnica de servicio, de modo que los registros del servidor de archivos no reflejan quién accede a
          través de ella: este registro es el único medio de saber quién consultó o descargó cada documento. Las
          búsquedas también se registran porque los resultados muestran fragmentos del texto de los documentos: sin
          ese registro, la lectura de información a través de los resultados no dejaría rastro.
        </p>
        <p>
          <strong>Lo que no hacemos.</strong> El registro de actividad no se utiliza para evaluar su desempeño ni
          para controlar su jornada, ni para elaborar perfiles, y no se toman decisiones basadas únicamente en
          tratamientos automatizados que le afecten (art. 22 RGPD). Solo se consulta de forma individualizada
          cuando es necesario para investigar un incidente de seguridad concreto o para atender un requerimiento de
          una autoridad competente, y cada consulta del registro queda, a su vez, registrada. Si la investigación
          de un incidente pusiera de manifiesto un uso indebido, la información podrá utilizarse en el
          procedimiento disciplinario o judicial que corresponda.
        </p>
      </Section>

      <Section n={4} title="¿Quién puede acceder a sus datos?">
        <ul className="list-disc pl-5 space-y-1">
          <li>Los administradores de la aplicación designados por el responsable, solo para los fines anteriores.</li>
          <li>
            El personal técnico de sistemas de la institución, en la medida necesaria para mantener los servidores
            y sujeto al deber de confidencialidad.
          </li>
          <li>
            En su caso, proveedores de servicios informáticos que actúen como encargados del tratamiento, con un
            contrato o acto jurídico conforme al art. 28 RGPD.
          </li>
          <li>
            En caso de incidente de seguridad, los organismos competentes en su gestión, como el CCN-CERT, conforme
            al Esquema Nacional de Seguridad.
          </li>
          <li>
            Juzgados y tribunales, Ministerio Fiscal, autoridades de protección de datos y demás órganos
            competentes, cuando exista una obligación legal.
          </li>
        </ul>
        <p>
          Los datos se tratan en servidores de la institución, dentro de su red interna: no se envían a servicios en
          la nube ni a servicios de inteligencia artificial de terceros, y no hay transferencias internacionales de
          datos.
        </p>
      </Section>

      <Section n={5} title="¿Cuánto tiempo conservamos sus datos?">
        <ul className="list-disc pl-5 space-y-1">
          <li>
            <strong>Sesión:</strong> hasta que cierra la sesión o pasan {days(p.session_days, 'es')} sin usar la
            aplicación. Sus grupos se vuelven a leer del Directorio Activo cada {p.groups_refresh_hours} horas.
          </li>
          <li>
            <strong>Registro de actividad:</strong>{' '}
            {audit > 0
              ? <>{days(audit, 'es')}; después se borra automáticamente.</>
              : <span className="bg-amber-100 text-amber-900 rounded px-1">sin plazo de borrado configurado (AUDIT_RETENTION_DAYS=0): debe fijarse uno.</span>}
          </li>
          {audit > 0 && (
            <li>
              <strong>Datos de su cuenta en la aplicación:</strong> hasta {days(audit, 'es')} después de su
              último inicio de sesión.
            </li>
          )}
          <li>
            <strong>Copias de seguridad:</strong> los datos anteriores pueden permanecer hasta{' '}
            {days(p.backup_keep_days, 'es')} más en las copias de seguridad, que se eliminan automáticamente.
          </li>
        </ul>
        <p>
          Cuando sean necesarios para investigar un incidente en curso, para un procedimiento disciplinario o
          judicial, o para atender las posibles responsabilidades derivadas del tratamiento, se conservarán durante
          el tiempo imprescindible y, en su caso, bloqueados conforme al art. 32 de la LOPDGDD.
        </p>
      </Section>

      <Section n={6} title="¿Está obligado a facilitar sus datos?">
        <p>
          Son necesarios para usar la aplicación: sin ellos no es posible identificarle ni aplicar sus permisos.
          Su uso no es imprescindible para su trabajo con los documentos, que siguen disponibles en las carpetas
          compartidas a través del Explorador de Windows.
        </p>
      </Section>

      <Section n={7} title="¿Cuáles son sus derechos?">
        <p>
          Puede ejercer sus derechos de acceso, rectificación, supresión, limitación del tratamiento y oposición
          (arts. 15 a 18 y 21 RGPD) dirigiéndose a {contact}, indicando el derecho que ejerce y acreditando su
          identidad. La portabilidad (art. 20 RGPD) solo procede respecto de los datos tratados para la ejecución de
          un contrato de trabajo. El ejercicio es gratuito y le responderemos en el plazo de un mes, prorrogable dos
          meses más en casos complejos (art. 12.3 RGPD).
        </p>
        <p>
          Algunos derechos pueden estar limitados: no se suprimirán los registros necesarios para cumplir una
          obligación legal o una misión de interés público, ni para la formulación, el ejercicio o la defensa de
          reclamaciones (art. 17.3 RGPD), y la oposición puede no prosperar cuando existan motivos imperiosos que
          prevalezcan, como la seguridad de los sistemas (art. 21.1 RGPD). Su nombre, correo y grupos se rectifican
          en el Directorio Activo, a través del servicio de informática; la aplicación los actualiza automáticamente.
        </p>
        <p>
          Si considera que no hemos atendido debidamente sus derechos, puede dirigirse, con carácter previo y
          voluntario, al Delegado de Protección de Datos (art. 37 LOPDGDD) y, en todo caso, presentar una
          reclamación ante la autoridad de control: <Authority p={p} />.
        </p>
      </Section>

      <Section n={8} title="Medidas de seguridad">
        <p>
          Entre otras: conexión cifrada (HTTPS); sesión guardada en una cookie inaccesible para el código de la
          página; contraseñas nunca almacenadas; permisos comprobados de nuevo con el servidor de archivos en cada
          descarga; acceso al registro de actividad restringido y, a su vez, registrado. La página no carga recursos
          de sitios externos, de modo que su navegación no se comunica a terceros.
        </p>
      </Section>

      <Section n={9} title="Uso de la aplicación y deber de confidencialidad">
        <ul className="list-disc pl-5 space-y-1">
          <li>Utilice la aplicación únicamente para el ejercicio de sus funciones.</li>
          <li>
            Los documentos pueden contener datos personales e información sujeta a reserva. Quien accede a ellos
            está obligado a guardar confidencialidad (art. 5 LOPDGDD) y la debida discreción sobre los asuntos que
            conozca por razón de su puesto (art. 53.12 del Estatuto Básico del Empleado Público), también después
            de cesar en él. Su utilización indebida puede constituir falta disciplinaria (art. 95 del mismo Estatuto).
          </li>
          <li>
            Las copias que descargue quedan bajo su responsabilidad: guárdelas solo en ubicaciones autorizadas por
            la institución, no las comparta por canales no autorizados y bórrelas cuando ya no las necesite. Para
            trabajar sobre un documento, ábralo en su ubicación original con «Copy network path».
          </li>
          <li>
            Si encuentra un documento al que cree que no debería tener acceso, no lo abra ni lo descargue y
            comuníquelo cuanto antes a {contact} o al servicio de informática: puede tratarse de un error de
            permisos que debe valorarse como posible incidente de seguridad (art. 33 RGPD).
          </li>
          <li>
            La aplicación refleja los permisos de Windows y no concede accesos propios. Los nombres, rutas y textos
            de los documentos se actualizan cada noche, de modo que un cambio reciente puede tardar hasta un día en
            reflejarse en las búsquedas; el permiso para abrir o descargar un fichero se comprueba siempre en el
            momento.
          </li>
          <li>
            La aplicación es una herramienta de apoyo: los resultados de búsqueda y el texto extraído de los
            documentos (incluido el obtenido por reconocimiento óptico de caracteres) pueden ser incompletos o
            contener errores. El documento original en la carpeta compartida es siempre la versión de referencia.
          </li>
        </ul>
      </Section>

      <Section n={10} title="Registro de actividades de tratamiento">
        <p>
          Este tratamiento figura en el Registro de Actividades de Tratamiento de la institución, publicado conforme
          al art. 31.2 de la LOPDGDD: <RecordLink p={p} />.
        </p>
      </Section>

      <Section n={11} title="Normativa aplicable">
        <p>
          Reglamento (UE) 2016/679, General de Protección de Datos (RGPD); Ley Orgánica 3/2018, de Protección de
          Datos Personales y garantía de los derechos digitales (LOPDGDD), en particular sus arts. 5, 11, 31 y 87 y su
          disposición adicional primera; Real Decreto Legislativo 5/2015, texto refundido del Estatuto Básico del
          Empleado Público, en particular su art. 14.j bis (intimidad en el uso de dispositivos digitales);
          art. 20.3 del Estatuto de los Trabajadores, para el personal laboral; art. 156 de la Ley 40/2015, de
          Régimen Jurídico del Sector Público, y Real Decreto 311/2022, por el que se regula el Esquema Nacional de
          Seguridad; y las políticas de seguridad de la información y de uso de medios tecnológicos de la
          institución.
        </p>
      </Section>

      <Section n={12} title="Cambios en este aviso">
        <p>
          Le informaremos en la propia aplicación de cualquier cambio relevante. Versión vigente: {NOTICE_VERSION.es}.
        </p>
      </Section>
    </>
  )
}

function NoticeEn({ p }: { p: PrivacyInfo }) {
  const contact = <Fact value={p.contact} setting="PRIVACY_CONTACT" />
  const audit = p.audit_retention_days
  return (
    <>
      <p className="text-sm bg-blue-50 border border-blue-100 text-blue-900 rounded-lg px-4 py-3">
        This is a translation for information. If it differs from the Spanish version, the Spanish version prevails.
      </p>

      <Section n={1} title="Who is the controller?">
        <p>
          <Fact value={p.controller} setting="PRIVACY_CONTROLLER" />, tax ID{' '}
          <Fact value={p.controller_id} setting="PRIVACY_CONTROLLER_ID" />, located at{' '}
          <Fact value={p.controller_address} setting="PRIVACY_CONTROLLER_ADDRESS" />.
          Contact for any data protection matter: {contact}.
        </p>
        <p>Data Protection Officer: <Fact value={p.dpo} setting="PRIVACY_DPO" />.</p>
      </Section>

      <Section n={2} title="What is Corp Library and what data about you does it process?">
        <p>
          Corp Library is a read-only internal tool to search and consult the documents on the department's shared
          folders. It doesn't create, change or delete documents, and everyone only sees what their Windows
          permissions already let them open. To work, it processes the following data about you:
        </p>
        <ul className="list-disc pl-5 space-y-1">
          <li>
            <strong>Identity and account:</strong> Windows username, full name, work email, your account's security
            identifier (SID) and the Active Directory groups you belong to.
          </li>
          <li>
            <strong>Session:</strong> date and time of sign-in and of your last activity, sign-in method (Windows
            sign-in or form), your computer's IP address and browser type.
          </li>
          <li>
            <strong>Activity log:</strong> sign-ins (including failed ones) and sign-outs; your searches, with the
            words searched and the filters used; the documents you view, preview or download, with their path; and
            attempts to open documents the file server refuses you.
          </li>
        </ul>
        <p>
          <strong>Source:</strong> identity and account data come from the institution's Active Directory; session
          and activity data are generated as you use the app. Your password is not stored: it is checked directly
          against Active Directory.
        </p>
        <p>
          We don't ask for special categories of data (GDPR art. 9). As searches are logged, please don't type
          personal data into the search box unless needed (for example, someone else's health data).
        </p>
      </Section>

      <Section n={3} title="Why do we process your data, and on what legal basis?">
        <Basis head={['Purpose', 'Legal basis']} rows={[
          [
            'Identifying you and applying your permissions, so you only see the documents you can open.',
            'Performance of a task carried out in the public interest or in the exercise of official authority: the ' +
            'management of the institution\'s documents by its staff (GDPR art. 6.1.e). For staff employed under an ' +
            'employment contract, also the performance of that contract (GDPR art. 6.1.b).',
          ],
          [
            'Keeping information secure through the activity log: detecting, investigating and documenting ' +
            'unauthorised access, incidents and breaches of the personal data the documents contain.',
            'Compliance with legal obligations (GDPR art. 6.1.c): GDPR art. 32, the first additional provision of ' +
            'the LOPDGDD and the Spanish National Security Framework (Royal Decree 311/2022), which requires public ' +
            'sector information systems to log their users\' activity.',
          ],
          [
            'Improving the service with aggregated statistics (for example, searches that find nothing), without ' +
            'identifying anyone.',
            'Task carried out in the public interest: improving the institution\'s services (GDPR art. 6.1.e).',
          ],
        ]} />
        <p>
          <strong>Why the activity log is necessary.</strong> The app opens files with a technical service account,
          so the file server's own logs don't show who accessed them through it: this log is the only way to know
          who viewed or downloaded each document. Searches are logged too because results show excerpts of the
          documents' text: without that record, reading information through search results would leave no trace.
        </p>
        <p>
          <strong>What we don't do.</strong> The activity log is not used to assess your performance or monitor your
          working hours, or to profile you, and no decision based solely on automated processing is taken about you
          (GDPR art. 22). Individual records are only consulted when needed to investigate a specific security
          incident or to comply with a request from a competent authority, and every query of the log is itself
          logged. If investigating an incident revealed misuse, the information may be used in the corresponding
          disciplinary or court proceedings.
        </p>
      </Section>

      <Section n={4} title="Who can access your data?">
        <ul className="list-disc pl-5 space-y-1">
          <li>The app administrators appointed by the controller, only for the purposes above.</li>
          <li>The institution's IT staff, as far as needed to maintain the servers, bound by confidentiality.</li>
          <li>
            Where applicable, IT service providers acting as processors under a contract or legal act meeting
            GDPR art. 28.
          </li>
          <li>
            In a security incident, the bodies competent to handle it, such as CCN-CERT, under the National Security
            Framework.
          </li>
          <li>
            Courts, the Public Prosecutor, data protection authorities and other competent bodies, where the law
            requires it.
          </li>
        </ul>
        <p>
          Data is processed on the institution's servers, inside its internal network: it is not sent to cloud
          services or third-party artificial intelligence services, and there are no international transfers.
        </p>
      </Section>

      <Section n={5} title="How long do we keep your data?">
        <ul className="list-disc pl-5 space-y-1">
          <li>
            <strong>Session:</strong> until you sign out or {days(p.session_days, 'en')} pass without using the app.
            Your groups are read again from Active Directory every {p.groups_refresh_hours} hours.
          </li>
          <li>
            <strong>Activity log:</strong>{' '}
            {audit > 0
              ? <>{days(audit, 'en')}; then it is deleted automatically.</>
              : <span className="bg-amber-100 text-amber-900 rounded px-1">no deletion period configured (AUDIT_RETENTION_DAYS=0): one must be set.</span>}
          </li>
          {audit > 0 && (
            <li><strong>Your account data in the app:</strong> up to {days(audit, 'en')} after your last sign-in.</li>
          )}
          <li>
            <strong>Backups:</strong> the data above may remain in backups for up to {days(p.backup_keep_days, 'en')}{' '}
            more; backups are deleted automatically.
          </li>
        </ul>
        <p>
          Where needed to investigate an ongoing incident, for disciplinary or court proceedings, or for liabilities
          arising from the processing, data is kept for as long as strictly necessary and, where applicable, blocked
          as required by LOPDGDD art. 32.
        </p>
      </Section>

      <Section n={6} title="Do you have to provide your data?">
        <p>
          It is needed to use the app: without it we can't identify you or apply your permissions. Using the app is
          not essential to your work with the documents, which remain available on the shared folders through
          Windows Explorer.
        </p>
      </Section>

      <Section n={7} title="What are your rights?">
        <p>
          You may exercise your rights of access, rectification, erasure, restriction and objection (GDPR arts. 15
          to 18 and 21) by writing to {contact}, stating the right you exercise and proving your identity.
          Portability (GDPR art. 20) only applies to data processed to perform an employment contract. It is free,
          and we will answer within one month, extendable by two further months for complex requests (GDPR art. 12.3).
        </p>
        <p>
          Some rights may be limited: records needed to comply with a legal obligation or a public interest task,
          or to establish, exercise or defend legal claims, won't be erased (GDPR art. 17.3), and an objection may
          not succeed where compelling grounds such as the security of the systems prevail (GDPR art. 21.1). Your
          name, email and groups are corrected in Active Directory, through IT; the app updates them automatically.
        </p>
        <p>
          If you believe we haven't properly handled your rights, you may first, voluntarily, contact the Data
          Protection Officer (LOPDGDD art. 37) and in any case complain to the supervisory authority: <Authority p={p} />.
        </p>
      </Section>

      <Section n={8} title="Security">
        <p>
          Among others: encrypted connection (HTTPS); the session is kept in a cookie the page's code can't read;
          passwords are never stored; permissions are checked again with the file server on every download; access
          to the activity log is restricted and itself logged. The page loads nothing from other sites, so your
          browsing isn't disclosed to third parties.
        </p>
      </Section>

      <Section n={9} title="Using the app, and confidentiality">
        <ul className="list-disc pl-5 space-y-1">
          <li>Use the app only to carry out your duties.</li>
          <li>
            Documents may contain personal data and information subject to confidentiality. Anyone who accesses them
            must keep them confidential (LOPDGDD art. 5) and show due discretion about matters known through their
            post (art. 53.12 of the Basic Statute of Public Employees), including after leaving it. Misuse may be a
            disciplinary offence (art. 95 of the same Statute).
          </li>
          <li>
            Copies you download are your responsibility: store them only where the institution allows, don't share
            them through unauthorised channels, and delete them when no longer needed. To work on a document, open it
            in its original location with "Copy network path".
          </li>
          <li>
            If you find a document you believe you shouldn't have access to, don't open or download it, and report
            it promptly to {contact} or IT: it may be a permissions error that must be assessed as a possible
            security incident (GDPR art. 33).
          </li>
          <li>
            The app mirrors Windows permissions and grants no access of its own. Document names, paths and text are
            updated nightly, so a recent change can take up to a day to show in searches; permission to open or
            download a file is always checked at that moment.
          </li>
          <li>
            The app is a support tool: search results and the text extracted from documents (including text read by
            optical character recognition) may be incomplete or contain errors. The original document on the shared
            folder is always the reference version.
          </li>
        </ul>
      </Section>

      <Section n={10} title="Record of processing activities">
        <p>
          This processing is listed in the institution's Record of Processing Activities, published under LOPDGDD
          art. 31.2: <RecordLink p={p} />.
        </p>
      </Section>

      <Section n={11} title="Applicable law">
        <p>
          Regulation (EU) 2016/679, the General Data Protection Regulation (GDPR); Spanish Organic Law 3/2018 on
          Personal Data Protection and Digital Rights (LOPDGDD), in particular arts. 5, 11, 31 and 87 and its first
          additional provision; Royal Legislative Decree 5/2015, the Basic Statute of Public Employees, in particular
          art. 14.j bis (privacy in the use of digital devices); art. 20.3 of the Workers' Statute, for staff under an
          employment contract; art. 156 of Law 40/2015 on the Legal Regime of the Public Sector, and Royal Decree
          311/2022 on the National Security Framework; and the institution's information security and technology use
          policies.
        </p>
      </Section>

      <Section n={12} title="Changes to this notice">
        <p>We will tell you in the app about any significant change. Current version: {NOTICE_VERSION.en}.</p>
      </Section>
    </>
  )
}

export default function PrivacyPage() {
  const [params, setParams] = useSearchParams()
  const lang: Lang = params.get('lang') === 'en' ? 'en' : 'es'
  const { data, isError } = usePrivacy()

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
        <div className="flex items-center justify-between gap-4">
          <Link to="/" className="inline-flex items-center gap-1 text-sm text-blue-700 hover:underline">
            <ArrowLeft className="w-4 h-4" /> {lang === 'es' ? 'Volver' : 'Back'}
          </Link>
          <div className="flex rounded-lg border border-gray-300 overflow-hidden text-sm" role="group" aria-label="Idioma / Language">
            {(['es', 'en'] as const).map((l) => (
              <button key={l} type="button" onClick={() => setParams(l === 'en' ? { lang: 'en' } : {})}
                      aria-pressed={lang === l}
                      className={lang === l ? 'px-3 py-1 bg-corp-navy text-white' : 'px-3 py-1 bg-white text-gray-700 hover:bg-gray-50'}>
                {l === 'es' ? 'Español' : 'English'}
              </button>
            ))}
          </div>
        </div>

        <article className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 sm:p-8 space-y-6">
          <header className="space-y-1">
            <h1 className="flex items-center gap-2 text-xl font-bold text-gray-900">
              <ShieldCheck className="w-6 h-6 text-corp-navy" />
              {lang === 'es' ? 'Aviso de privacidad de Corp Library' : 'Corp Library privacy notice'}
            </h1>
            <p className="text-xs text-gray-500">
              {lang === 'es'
                ? 'Información sobre protección de datos conforme a los arts. 13 y 14 del Reglamento (UE) 2016/679 y al art. 11 de la Ley Orgánica 3/2018.'
                : 'Data protection information under arts. 13 and 14 of Regulation (EU) 2016/679 and art. 11 of Spanish Organic Law 3/2018.'}
            </p>
          </header>
          {isError && (
            <p className="text-sm bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3">
              {lang === 'es'
                ? 'No se han podido cargar los datos del responsable. Inténtelo de nuevo más tarde.'
                : "The controller's details couldn't be loaded. Please try again later."}
            </p>
          )}
          {/* Only with the facts loaded: retention periods must never be shown wrong, even briefly. */}
          {data ? (lang === 'es' ? <NoticeEs p={data} /> : <NoticeEn p={data} />) : !isError && <Loading />}
        </article>
      </div>
    </div>
  )
}
