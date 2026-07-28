import PropTypes from "prop-types";
import "../styles/portal.css";

export default function BlindReviewToggle({ enabled, onToggle }) {
  return (
    <label className="blind-toggle">
      <input type="checkbox" checked={enabled} onChange={onToggle} />
      <span className="blind-toggle-slider" />
      <span className="blind-toggle-label">Blind Review</span>
    </label>
  );
}

BlindReviewToggle.propTypes = {
  enabled: PropTypes.bool,
  onToggle: PropTypes.func,
};
