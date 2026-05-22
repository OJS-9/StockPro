import { useTranslation } from 'react-i18next'
import LegalLayout from './LegalLayout'

const SECTION_KEYS = [
  'operator',
  'dataCollected',
  'subprocessors',
  'retention',
  'rights',
  'cookies',
  'children',
  'changes',
] as const

export default function Privacy() {
  const { t } = useTranslation()

  const sections = SECTION_KEYS.map(key => ({
    title: t(`legal.privacy.sections.${key}.title`),
    body: t(`legal.privacy.sections.${key}.body`),
  }))

  return (
    <LegalLayout
      title={t('legal.privacy.title')}
      lastUpdated={t('legal.lastUpdated')}
      intro={t('legal.privacy.intro')}
      sections={sections}
      contactEmail={t('legal.contactEmail')}
    />
  )
}
