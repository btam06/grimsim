import { faChevronDown } from '@fortawesome/free-solid-svg-icons'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import Accordion from '@mui/material/Accordion'
import AccordionDetails from '@mui/material/AccordionDetails'
import AccordionSummary from '@mui/material/AccordionSummary'

// A card's rules text, collapsed until opened.
function CardTextAccordion({ text, label = 'Card text' }) {
  if (!text) return null
  return (
    <Accordion className="card-accordion" disableGutters elevation={0} square>
      <AccordionSummary expandIcon={<FontAwesomeIcon icon={faChevronDown} />}>
        {label}
      </AccordionSummary>
      <AccordionDetails className="card-text">{text}</AccordionDetails>
    </Accordion>
  )
}

export default CardTextAccordion
