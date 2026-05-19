const Product = [
  {id:1,title:'a'},
  {id:2,title:'b'},
  {id:3,title:'c'}
  ];
export default function goods(){
    const listItem=Product.map(item=>{
    <li key={item.id}>
      {item.title}
    </li>
  })

  return (
    <ul>{listItem}</ul>
  );
}
