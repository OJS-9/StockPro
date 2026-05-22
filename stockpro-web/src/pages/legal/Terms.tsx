import { useTranslation } from 'react-i18next'
import LegalLayout from './LegalLayout'

const SECTION_KEYS = [
  'acceptance',
  'service',
  'acceptableUse',
  'subscriptions',
  'intellectualProperty',
  'liability',
  'termination',
  'governingLaw',
] as const

export default function Terms() {
  const { t } = useTranslation()

  const sections = SECTION_KEYS.map(key => ({
    title: t(`legal.terms.sections.${key}.title`),
    body: t(`legal.terms.sections.${key}.body`),
  }))

  return (
    <LegalLayout
      title={t('legal.terms.title')}
      lastUpdated={t('legal.lastUpdated')}
      intro={t('legal.terms.intro')}
      disclaimer={t('legal.terms.disclaimer')}
      sections={sections}
      contactEmail={t('legal.contactEmail')}
    />
  )
}
