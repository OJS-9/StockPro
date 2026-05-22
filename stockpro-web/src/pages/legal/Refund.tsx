import { useTranslation } from 'react-i18next'
import LegalLayout from './LegalLayout'

const SECTION_KEYS = [
  'guarantee',
  'howToRequest',
  'afterWindow',
  'freeTier',
  'disputes',
] as const

export default function Refund() {
  const { t } = useTranslation()

  const sections = SECTION_KEYS.map(key => ({
    title: t(`legal.refund.sections.${key}.title`),
    body: t(`legal.refund.sections.${key}.body`),
  }))

  return (
    <LegalLayout
      title={t('legal.refund.title')}
      lastUpdated={t('legal.lastUpdated')}
      intro={t('legal.refund.intro')}
      sections={sections}
      contactEmail={t('legal.contactEmail')}
    />
  )
}
