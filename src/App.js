import { useDispatch, useSelector } from "react-redux";
import { decrement, increment } from "./Redux/action";


function App() {
  const counter = useSelector((state) => state);
  const dispatch = useDispatch()

  return (
    <div>
      <div classname="counter">
        <h1>Counter: {counter}</h1>
        <button onClick={()=> dispatch(increment())}>Increment</button>
        <button disabled={counter === 0 ? true : false} onClick={()=> dispatch(decrement())}>Decrement</button>
      </div>
    </div>
  );
}

export default App;
