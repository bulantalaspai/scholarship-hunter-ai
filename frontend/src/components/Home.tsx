import { useState } from 'react'
import ConnectionCheck from './ConnectionCheck'

const subjects = ['Engineering', 'Computer Science', 'Data Science']

const paths = [
  { title: 'Explore the catalogue', description: 'Compare destinations, funding and deadlines.', href: '#/explore' },
  { title: 'Check your eligibility', description: 'See which requirements your academic profile meets.', href: '#/profile' },
  { title: 'Ask Local AI', description: 'Request a shortlist with evidence for each selection.', href: '#/agent' },
]

export default function Home() {
  const [field, setField] = useState('')

  return (
    <>
      <div className="home-running-head">
        <p className="home-audience">For students applying from Kazakhstan</p>
        <ConnectionCheck />
      </div>
      <section className="home-hero" aria-labelledby="home-title">
        <div className="hero-copy">
          <h1 id="home-title">A field guide to master’s funding.</h1>
          <p className="hero-description">
            Find scholarships abroad, compare what they cover, and check your
            eligibility against official sources.
          </p>
          <form className="home-search" onSubmit={(event) => {
            event.preventDefault()
            const params = new URLSearchParams(field.trim() ? { field: field.trim() } : {})
            window.location.hash = `/explore?${params}`
          }}>
            <label htmlFor="home-field">What would you like to study?</label>
            <div className="hero-search-controls">
              <span className="search-lens" aria-hidden="true" />
              <input id="home-field" value={field} maxLength={100}
                placeholder="Enter a field of study"
                onChange={(event) => setField(event.target.value)} />
              <button type="submit" aria-label="Explore scholarships">
                <span>Explore<span className="search-action-detail"> scholarships</span></span>
              </button>
            </div>
            <div className="field-shortcuts" aria-label="Browse by field">
              {subjects.map(subject => (
                <a key={subject} href={`#/explore?${new URLSearchParams({ field: subject })}`}>{subject}</a>
              ))}
            </div>
          </form>
        </div>
        <figure className="hero-print">
          <div className="print-arch">
            <img src="/radcliffe-library.jpg" alt="Engraved view of the domed Radcliffe Camera in Oxford"
              width="1200" height="788" fetchPriority="high" />
          </div>
          <figcaption>
            <span>Radcliffe Camera, Oxford</span>
            <a href="https://wellcomecollection.org/works/kpu9usad" target="_blank" rel="noreferrer">Wellcome Collection</a>
          </figcaption>
        </figure>
      </section>
      <section className="home-directory" aria-labelledby="directory-title">
        <h2 id="directory-title">From search<br /> to shortlist.</h2>
        <ul>
          {paths.map(item => (
            <li key={item.href}>
              <a href={item.href}>
                <span className="directory-title">{item.title}</span>
                <span className="directory-description">{item.description}</span>
                <span className="directory-arrow" aria-hidden="true">↗</span>
              </a>
            </li>
          ))}
        </ul>
      </section>
    </>
  )
}
