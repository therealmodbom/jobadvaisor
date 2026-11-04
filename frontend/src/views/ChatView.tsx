import { useState, type FormEvent } from 'react'
import { ExternalLink, LoaderCircle, Search, Send } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api } from '@/api'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/input'

type Message = { role: 'user' | 'assistant'; content: string; steps?: string[] }

/** German names of the agent's tools, shown as the steps an answer took. */
const STEPS: Record<string, string> = {
  find_postings: 'Anzeigen gesucht',
  best_open_postings: 'Beste offene Anzeigen gesucht',
  check_exclusions: 'Ausschlussregeln geprüft',
  extract_features: 'Merkmale gelesen',
  find_similar_postings: 'Ähnliche Anzeigen gesucht',
  score_posting: 'Score berechnet',
  rescore_postings: 'Scores neu berechnet',
  research_company: 'Firma nachgeschlagen',
  fetch_posting: 'Anzeige abgerufen',
}

/** Styles for the elements GitHub-flavoured Markdown produces, which Tailwind's preflight resets. */
const MARKDOWN = cn('flex flex-col gap-3 [&_li]:mt-1 [&_ol]:list-decimal [&_ol]:pl-6 [&_ul]:list-disc [&_ul]:pl-6',
  '[&_h1]:text-xl [&_h1]:font-bold [&_h2]:text-lg [&_h2]:font-bold [&_h3]:font-bold',
  '[&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:font-mono [&_code]:text-[0.9em]',
  '[&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:bg-muted [&_pre]:p-3',
  '[&_blockquote]:border-l-4 [&_blockquote]:pl-3 [&_blockquote]:text-muted-foreground',
  '[&_table]:border-collapse [&_td]:border [&_td]:px-2.5 [&_td]:py-1.5 [&_td]:align-top',
  '[&_th]:border [&_th]:bg-muted [&_th]:px-2.5 [&_th]:py-1.5 [&_th]:text-left')

/** Link look as elsewhere in the app (`OriginalLink`): colour and underline, so a link is not
 * marked by colour alone. */
const LINK = 'text-primary underline underline-offset-2'

/** The agent's answer as GitHub-flavoured Markdown. Raw HTML is not rendered and unsafe link
 * protocols are dropped (react-markdown's defaults); a link into the app (`#/…`, such as a
 * posting page) opens in the same tab, every other link in a new one, marked with an icon and
 * a screen-reader note. */
function Answer({ text }: { text: string }) {
  return (
    <div className={MARKDOWN}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
        a: ({ node: _node, children, ...props }) => props.href?.startsWith('#/')
          ? <a {...props} className={LINK}>{children}</a>
          : (
            <a {...props} target="_blank" rel="noreferrer" className={LINK}>
              {children}
              <ExternalLink className="ml-0.5 inline size-3.5 align-[-0.1em]" aria-hidden="true" />
              <span className="sr-only"> (öffnet in neuem Tab)</span>
            </a>
          ),
        table: ({ node: _node, ...props }) => <div className="overflow-x-auto"><table {...props} /></div>,
      }}>
        {text}
      </ReactMarkdown>
    </div>
  )
}

const SUGGESTIONS = ['Auf welche Stelle soll ich mich bewerben?', 'Was habe ich als zu junior markiert?',
                     'Warum wurde eine Anzeige ausgeschlossen?', 'Warum hat eine Anzeige ihren Score bekommen?']

/** The chat view: questions to the agent about the pool's postings, scores and ratings, sent
 * with the whole conversation through `POST /agent/messages`. */
export function ChatView() {
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState('')
  const [pending, setPending] = useState(false)
  const [failed, setFailed] = useState(false)

  async function send(conversation: Message[]) {
    setPending(true)
    setFailed(false)
    try {
      const answer = await api<{ reply: string; tool_calls: { name: string }[] }>('/agent/messages', {
        method: 'POST',
        json: { messages: conversation.map(({ role, content }) => ({ role, content })) },
      })
      const steps = [...new Set(answer.tool_calls.map((call) => STEPS[call.name] ?? call.name))]
      setMessages([...conversation, { role: 'assistant', content: answer.reply, steps }])
    } catch {
      setFailed(true)
    } finally {
      setPending(false)
    }
  }

  /** Send `text` as the user's next question; false when there was nothing to send or an
   * answer is still pending. */
  function ask(text: string): boolean {
    const question = text.trim()
    if (!question || pending) return false
    const conversation: Message[] = [...messages, { role: 'user', content: question }]
    setMessages(conversation)
    void send(conversation)
    return true
  }

  function submit(event?: FormEvent) {
    event?.preventDefault()
    if (ask(draft)) setDraft('')
  }

  return (
    <div className="mx-auto flex max-w-[820px] flex-col gap-6">
      <div>
        <h1 className="text-3xl leading-tight font-bold tracking-tight">Fragen zu deinen Anzeigen</h1>
        <p className="mt-1.5 text-muted-foreground">
          Der Agent kennt deine Anzeigen, ihre Scores und deine Bewertungen. Er empfiehlt, worauf du dich
          bewerben kannst, und erklärt Scores und Ausschlüsse, bewertet aber nie für dich.
        </p>
      </div>

      <section aria-label="Unterhaltung" className="flex flex-col gap-5">
        {messages.map((message, index) => message.role === 'user' ? (
          <div key={index} className="max-w-[78%] self-end rounded-[14px_14px_4px_14px] bg-positive-soft px-3.5 py-2.5">
            <span className="sr-only">Du: </span>{message.content}
          </div>
        ) : (
          <div key={index} className="flex max-w-[68ch] flex-col gap-2">
            {message.steps && message.steps.length > 0 && (
              <ul aria-label="Schritte des Agenten" className="flex flex-wrap gap-1.5">
                {message.steps.map((step) => (
                  <li key={step} className="inline-flex items-center gap-1.5 rounded-full bg-muted py-0.5 pr-2.5 pl-2 text-[13px] text-muted-foreground">
                    <Search className="size-3.5" aria-hidden="true" />{step}
                  </li>
                ))}
              </ul>
            )}
            <span className="sr-only">Agent: </span><Answer text={message.content} />
          </div>
        ))}
        {failed && (
          <div role="alert" className="flex max-w-[68ch] flex-wrap items-center gap-x-4 gap-y-2.5 rounded-xl border border-danger bg-danger-soft px-4 py-3.5">
            <p className="flex-[1_1_280px]"><strong>Keine Antwort.</strong> Die Anfrage ist fehlgeschlagen. Deine Frage bleibt erhalten.</p>
            <Button variant="outline" onClick={() => void send(messages)}>Erneut versuchen</Button>
          </div>
        )}
        {pending && (
          <div role="status" className="inline-flex items-center gap-2.5 text-muted-foreground">
            <LoaderCircle className="size-[18px] motion-safe:animate-spin" aria-hidden="true" />Sieht deine Anzeigen durch…
          </div>
        )}
      </section>

      <form onSubmit={submit} className="flex flex-col gap-2.5 border-t pt-4">
        <div className="flex flex-wrap gap-2">
          {SUGGESTIONS.map((suggestion) => (
            <button key={suggestion} type="button" onClick={() => ask(suggestion)} disabled={pending}
                    className="min-h-10 rounded-full border bg-card px-3.5 text-sm disabled:opacity-50">
              {suggestion}
            </button>
          ))}
        </div>
        <label htmlFor="chat-input" className="sr-only">Deine Frage</label>
        <div className="flex items-end gap-2 rounded-xl border border-input bg-card p-2 shadow-card">
          <Textarea id="chat-input" rows={2} value={draft} onChange={(event) => setDraft(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' && !event.shiftKey) submit(event)
                    }}
                    placeholder="Frag, warum eine Anzeige niedrig bewertet ist, was eine Regel tut oder wie du früher bewertet hast"
                    className="min-w-0 flex-1 resize-none border-0 bg-transparent" />
          <Button type="submit" disabled={pending}><Send className="size-4" aria-hidden="true" />Senden</Button>
        </div>
      </form>
    </div>
  )
}
