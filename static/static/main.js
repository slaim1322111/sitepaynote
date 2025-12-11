// Небольшие UI‑помощники для Маркетплейса нот
document.addEventListener('DOMContentLoaded', function(){
  // auto-dismiss non-danger alerts after 4s
  document.querySelectorAll('.alert').forEach(function(el){
    if (!el.classList.contains('alert-danger')){
      setTimeout(function(){
        try{ var bs = bootstrap.Alert.getOrCreateInstance(el); bs.close(); } catch(e){}
      }, 4000);
    }
  });
});
