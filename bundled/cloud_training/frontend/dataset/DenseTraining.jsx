import DenseModePicker from './DenseModePicker';
import DenseRecipePanel from './DenseRecipePanel';
import DenseModelsPanel from './DenseModelsPanel';
export default function DenseTraining({ placement, ...props }) {
  if (placement === 'mode') return <DenseModePicker {...props} />;
  if (placement === 'recipe') return <DenseRecipePanel {...props} />;
  if (placement === 'models') return <DenseModelsPanel {...props} />;
  return null;
}
