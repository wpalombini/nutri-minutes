import Link from 'next/link'
import { Fragment, type ReactNode } from 'react'
import { type Block, formatUpdated, type Inline, type ProseDocument } from '@/lib/prose'
import styles from './ProsePage.module.css'

function renderInline(nodes: Inline[]): ReactNode {
  return nodes.map((node, index) => {
    const key = `${index}-${node.type}`
    if (node.type === 'text') return <Fragment key={key}>{node.text}</Fragment>
    if (node.type === 'bold') return <strong key={key}>{renderInline(node.children)}</strong>
    return node.href.startsWith('/') ? (
      <Link key={key} href={node.href}>
        {renderInline(node.children)}
      </Link>
    ) : (
      <a key={key} href={node.href} rel="noopener noreferrer">
        {renderInline(node.children)}
      </a>
    )
  })
}

function renderBlock(block: Block, index: number): ReactNode {
  switch (block.type) {
    case 'heading': {
      const Heading = block.level === 2 ? 'h2' : 'h3'
      return <Heading key={index}>{renderInline(block.children)}</Heading>
    }
    case 'paragraph':
      return <p key={index}>{renderInline(block.children)}</p>
    case 'list': {
      const List = block.ordered ? 'ol' : 'ul'
      return (
        <List key={index}>
          {block.items.map((item, i) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: static content, never reordered
            <li key={i}>{renderInline(item)}</li>
          ))}
        </List>
      )
    }
  }
}

/**
 * The prose page template (design/screens/app-shell.md). The spec doesn't place the "Last
 * updated" line, so it goes after the body, in `type.meta`.
 */
export function ProsePage({ page }: { page: ProseDocument }) {
  return (
    <>
      <h1 className={styles.title}>{page.title}</h1>
      <div className={styles.prose}>{page.blocks.map(renderBlock)}</div>
      <p className={styles.updated}>
        Last updated <time dateTime={page.updated}>{formatUpdated(page.updated)}</time>
      </p>
    </>
  )
}
