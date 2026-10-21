import { faChevronDown } from '@fortawesome/free-solid-svg-icons'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import Accordion from '@mui/material/Accordion'
import AccordionDetails from '@mui/material/AccordionDetails'
import AccordionSummary from '@mui/material/AccordionSummary'

// A card's rules text (or any other content, as children), collapsed until
// opened.
function CardTextAccordion({ text, label = 'Card text', children, className = '' }) {
  if (!text && !children) return null
  return (
    <Accordion
      className={`card-accordion ${className}`.trim()}
      disableGutters
      elevation={0}
      square
    >
      <AccordionSummary expandIcon={<FontAwesomeIcon icon={faChevronDown} />}>
        {label}
      </AccordionSummary>
      <AccordionDetails className="card-text">{children ?? text}</AccordionDetails>
    </Accordion>
  )
}

export default CardTextAccordion
