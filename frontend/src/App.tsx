import { useEffect, useRef, useState } from 'react'
import type { StudentProfile } from './types'
import { useHashRoute } from './hooks'
import {
  EligibilityPage,
  Explorer,
  MatchesPage,
  ScholarshipDetails,
} from './pages'
import ProfileForm from './components/ProfileForm'
import Home from './components/Home'
import AgentRecommendations from './components/AgentRecommendations'
import ReviewDashboard from './components/ReviewDashboard'
import { EmptyState } from './components/ui'

function validId(value: string | null) {
  if (!value || !/^\d+$/.test(value)) return null
  const number = Number(value)
  return Number.isSafeInteger(number) && number > 0 ? number : null
}

export default function App() {
  const hash = useHashRoute()
  const previousHash = useRef(hash)
  const [profile, setProfile] = useState<StudentProfile>()
  const [pathname, query = ''] = hash.slice(1).split('?')
  const path = pathname || '/'
  const params = new URLSearchParams(query)
  const scholarship = validId(params.get('scholarship'))
  const aiMode = params.get('mode') === 'ai'
  const detail = /^\/scholarships\/(\d+)$/.exec(path)
  const result = /^\/results\/(\d+)$/.exec(path)
  const id = validId(detail?.[1] ?? result?.[1] ?? null)
  const matchPage = Number(params.get('page') ?? 1)

  useEffect(() => {
    if (previousHash.current === hash) return
    previousHash.current = hash
    document.documentElement.scrollTop = 0
    document.getElementById('main-content')?.focus({ preventScroll: true })
  }, [hash])

  let content
  if (path === '/') content = <Home />
  else if (path === '/review') content = <ReviewDashboard />
  else if (path === '/explore') content = <Explorer key={query} query={query} />
  else if (detail && id) content = <ScholarshipDetails id={id} />
  else if (path === '/profile' && (!params.has('scholarship') || scholarship))
    content = (
      <>
        <header className="page-heading profile-heading">
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
              {aiMode
                ? 'Your profile for local AI'
                : scholarship
                  ? 'Check your eligibility'
                  : 'Your student profile'}
            </h1>
            <p>
              {aiMode
                ? 'Add your study details here. You choose when to ask the local AI for recommendations.'
                : scholarship
                  ? 'Compare your background with this scholarship’s documented requirements.'
                  : 'Compare your academic background and study plans with published scholarship requirements.'}
            </p>
          </div>
          <aside className="profile-aside">
            <details className="profile-privacy">
              <summary>
                <span className="profile-privacy-icon" aria-hidden="true" />
                Your profile stays local
              </summary>
              <p>
                Your details stay in this tab and go to the local application
                when you request a check. No name, email, account or documents are needed.
              </p>
            </details>
            {profile && (
              <button
                className="button-text profile-clear"
                onClick={() => {
                  setProfile(undefined)
                  window.location.hash = aiMode
                    ? '/profile?mode=ai'
                    : '/profile'
                }}
              >
                Clear profile
              </button>
            )}
          </aside>
        </header>
        <ProfileForm
          key={`${aiMode ? 'ai' : (scholarship ?? 'matches')}:${profile ? 'saved' : 'empty'}`}
          initialProfile={profile}
          submitLabel={
            aiMode
              ? 'Continue to local AI'
              : scholarship
                ? 'Check my eligibility'
                : 'Find my matches'
          }
          onSubmit={(value) => {
            setProfile(value)
            window.location.hash = aiMode
              ? '/agent'
              : scholarship
                ? `/results/${scholarship}`
                : '/matches'
          }}
        />
      </>
    )
  else if (path === '/agent')
    content = profile ? (
      <AgentRecommendations key={JSON.stringify(profile)} profile={profile} />
    ) : (
      <EmptyState title="Add your profile for local AI">
        <p>
          Your academic profile is kept only in memory. Add it first, then
          explicitly request local AI recommendations.
        </p>
        <a className="button" href="#/profile?mode=ai">
          Add student profile
        </a>
        <p>
          <a href="#/explore">Or browse scholarships without a profile</a>
        </p>
      </EmptyState>
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
            <span className="brand-mark" aria-hidden="true">S</span>
            <span>
              Scholarship Hunter<span className="brand-ai">AI</span>
            </span>
          </a>
          <nav aria-label="Main navigation">
            <a
              href="#/explore"
              aria-label="Explore scholarships"
              aria-current={path === '/explore' || detail ? 'page' : undefined}
            >
              <span>Explore<span className="nav-detail"> scholarships</span></span>
            </a>
            <a
              href="#/profile"
              aria-label="My profile"
              aria-current={path === '/profile' ? 'page' : undefined}
            >
              Profile
            </a>
            {profile && (
              <a
                href="#/matches"
                aria-label="My matches"
                aria-current={
                  path === '/matches' || result ? 'page' : undefined
                }
              >
                Matches
              </a>
            )}
            <a
              className="nav-ai"
              href="#/agent"
              aria-current={path === '/agent' ? 'page' : undefined}
            >
              <span aria-hidden="true">✦</span>
              Local AI
            </a>
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
        <div className="footer-inner">
          <div>
            <a className="footer-brand" href="#/">
              Scholarship Hunter AI
            </a>
            <p>
              International master’s scholarships for students from Kazakhstan.
            </p>
          </div>
          <p className="footer-note">
            Eligibility checks cannot guarantee admission or funding.
          </p>
          <a href="#/explore">Explore the catalogue</a>
        </div>
      </footer>
    </div>
  )
}
