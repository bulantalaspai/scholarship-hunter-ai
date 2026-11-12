import { useEffect, useState } from 'react'
import type { StudentProfile } from './types'
import { useHashRoute } from './hooks'
import {
  EligibilityPage,
  Explorer,
  Home,
  MatchesPage,
  ScholarshipDetails,
} from './pages'
import ProfileForm from './components/ProfileForm'
import { EmptyState } from './components/ui'

function validId(value: string | null) {
  if (!value || !/^\d+$/.test(value)) return null
  const number = Number(value)
  return Number.isSafeInteger(number) && number > 0 ? number : null
}

export default function App() {
  const hash = useHashRoute()
  const [profile, setProfile] = useState<StudentProfile>()
  const [pathname, query = ''] = hash.slice(1).split('?')
  const path = pathname || '/'
  const params = new URLSearchParams(query)
  const scholarship = validId(params.get('scholarship'))
  const detail = /^\/scholarships\/(\d+)$/.exec(path)
  const result = /^\/results\/(\d+)$/.exec(path)
  const id = validId(detail?.[1] ?? result?.[1] ?? null)
  const matchPage = Number(params.get('page') ?? 1)

  useEffect(() => {
    document.getElementById('main-content')?.focus()
  }, [hash])

  let content
  if (path === '/') content = <Home />
  else if (path === '/explore') content = <Explorer key={query} query={query} />
  else if (detail && id) content = <ScholarshipDetails id={id} />
  else if (path === '/profile' && (!params.has('scholarship') || scholarship))
    content = (
      <>
        <div className="page-heading">
          <div>
            <p className="breadcrumb">
              <a
                href={
                  scholarship ? `#/scholarships/${scholarship}` : '#/explore'
                }
              >
                {scholarship ? 'Scholarship details' : 'Scholarship explorer'}
              </a>{' '}
              / My profile
            </p>
            <h1>
              {scholarship ? 'Check your eligibility' : 'Your student profile'}
            </h1>
            <p>
              {scholarship
                ? 'Compare your background with this scholarship’s documented requirements.'
                : 'Tell us about your studies to find and understand your matches.'}
            </p>
          </div>
        </div>
        <div className="profile-layout">
          <ProfileForm
            key={`${scholarship ?? 'matches'}:${profile ? 'saved' : 'empty'}`}
            initialProfile={profile}
            submitLabel={
              scholarship ? 'Check my eligibility' : 'Find my matches'
            }
            onSubmit={(value) => {
              setProfile(value)
              window.location.hash = scholarship
                ? `/results/${scholarship}`
                : '/matches'
            }}
          />
          <aside className="profile-aside">
            <h2>Only what’s needed.</h2>
            <p>
              No name, email, account, or documents. Your profile is held in
              this browser tab’s memory and sent only to the local application
              when you request a check.
            </p>
            <p>
              Leave optional scores blank when you don’t have them. Missing
              information stays unknown.
            </p>
            {profile && (
              <button
                className="button-secondary"
                onClick={() => {
                  setProfile(undefined)
                  window.location.hash = '/profile'
                }}
              >
                Clear profile
              </button>
            )}
          </aside>
        </div>
      </>
    )
  else if (
    (result && id) ||
    (path === '/matches' &&
      Number.isInteger(matchPage) &&
      matchPage >= 1 &&
      matchPage <= 1_000_000)
  ) {
    content = !profile ? (
      <EmptyState title="Add your profile to continue">
        <p>
          Your profile is kept only in memory, so refreshing the page clears it.
          Add your study details to request a new comparison.
        </p>
        <a
          className="button"
          href={id ? `#/profile?scholarship=${id}` : '#/profile'}
        >
          Add student profile
        </a>
      </EmptyState>
    ) : result && id ? (
      <EligibilityPage id={id} profile={profile} />
    ) : (
      <MatchesPage profile={profile} page={matchPage} />
    )
  } else
    content = (
      <EmptyState title="Page not found">
        <p>
          This link may be incomplete. Return to the catalogue to find a
          scholarship.
        </p>
        <a className="button" href="#/explore">
          Explore scholarships
        </a>
      </EmptyState>
    )

  return (
    <div className="app-shell">
      <a
        className="skip-link"
        href="#main-content"
        onClick={(event) => {
          event.preventDefault()
          document.getElementById('main-content')?.focus()
        }}
      >
        Skip to content
      </a>
      <header className="site-header">
        <div className="header-inner">
          <a
            className="brand"
            href="#/"
            aria-label="Scholarship Hunter AI home"
          >
            <span className="brand-mark" aria-hidden="true">
              SH
            </span>
            <span>
              Scholarship Hunter<span className="brand-ai">AI</span>
            </span>
          </a>
          <nav aria-label="Main navigation">
            <a
              href="#/explore"
              aria-current={path === '/explore' || detail ? 'page' : undefined}
            >
              Explore scholarships
            </a>
            <a
              href="#/profile"
              aria-current={path === '/profile' ? 'page' : undefined}
            >
              My profile
            </a>
            {profile && (
              <a
                href="#/matches"
                aria-current={
                  path === '/matches' || result ? 'page' : undefined
                }
              >
                My matches
              </a>
            )}
          </nav>
        </div>
      </header>
      <main
        id="main-content"
        tabIndex={-1}
        className={`main-content ${path === '/' ? 'home-page' : ''}`}
      >
        {content}
      </main>
      <footer className="site-footer">
        <div>
          <a className="footer-brand" href="#/">
            Scholarship Hunter AI
          </a>
          <p>A clearer next step for students in Kazakhstan.</p>
        </div>
        <p>
          Official sources. Transparent checks.
          <br />
          No guarantee of admission or funding.
        </p>
        <a href="#/explore">Explore the catalogue</a>
      </footer>
    </div>
  )
}
