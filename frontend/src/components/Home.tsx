import { useState } from 'react'
import ConnectionCheck from './ConnectionCheck'

const steps = [
  {
    name: 'Discover',
    icon: 'search',
    description: 'Browse scholarships by destination, field, and funding.',
  },
  {
    name: 'Understand',
    icon: 'paper',
    description: 'Compare your academic profile with documented requirements.',
  },
  {
    name: 'Decide',
    icon: 'check',
    description: 'See which conditions you meet and which need more evidence.',
  },
] as const

export default function Home() {
  const [field, setField] = useState('')

  return (
    <>
      <ConnectionCheck />
      <section className="home-hero" aria-labelledby="home-title">
        <div className="hero-copy">
          <p className="hero-audience">For students applying from Kazakhstan</p>
          <h1 id="home-title">Find funding for your master’s abroad.</h1>
          <p className="hero-description">
            Explore scholarships from official providers and see how the
            requirements fit your academic profile.
          </p>
          <form
            className="home-search"
            onSubmit={(event) => {
              event.preventDefault()
              const studyField = field.trim()
              const params = new URLSearchParams(
                studyField ? { field: studyField } : {},
              )
              window.location.hash = `/explore?${params}`
            }}
          >
            <label htmlFor="home-field">What would you like to study?</label>
            <div className="hero-search-controls">
              <div className="hero-input-wrap">
                <span className="home-icon icon-search" aria-hidden="true" />
                <input
                  id="home-field"
                  value={field}
                  onChange={(event) => setField(event.target.value)}
                  maxLength={100}
                  placeholder="e.g. Engineering"
                />
              </div>
              <button type="submit">Explore scholarships</button>
            </div>
          </form>
          <a className="hero-profile-link" href="#/profile">
            Start with your student profile <span aria-hidden="true">→</span>
          </a>
        </div>
        <div className="hero-visual">
          <img
            src="/campus-1080.webp"
            srcSet="/campus-640.webp 640w, /campus-1080.webp 1080w"
            sizes="(max-width: 760px) calc(100vw - 36px), (max-width: 1260px) 42vw, 520px"
            alt=""
            width="1080"
            height="810"
            fetchPriority="high"
          />
          <div className="hero-evidence">
            <span className="hero-evidence-mark" aria-hidden="true">
              <span className="home-icon icon-check" />
            </span>
            <div>
              <strong>Official sources, always in view</strong>
              <p>Every listing shows a provider link and verification date.</p>
            </div>
          </div>
        </div>
      </section>
      <section className="home-journey" aria-labelledby="home-journey-title">
        <h2 id="home-journey-title">From search to shortlist</h2>
        <ol className="home-steps">
          {steps.map(({ name, icon, description }) => (
            <li key={name}>
              <span className="home-step-mark" aria-hidden="true">
                <span className={`home-icon icon-${icon}`} />
              </span>
              <div>
                <h3>{name}</h3>
                <p>{description}</p>
              </div>
            </li>
          ))}
        </ol>
        <p className="home-privacy">
          Your profile stays in this tab. No account is needed.
        </p>
      </section>
    </>
  )
}
