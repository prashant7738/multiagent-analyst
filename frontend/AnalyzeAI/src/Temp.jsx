import React from 'react'
import { SpotlightNavbar } from "@/components/ui/spotlight-navbar"
import SocialFlipButton from "@/components/ui/social-flip-button"
import {LiquidText} from "@/components/ui/liquid-text"
import Bg from './Bg'
const Temp = () => {
   return (
    <>
        <div className=''>
    
    <SpotlightNavbar 
      items={[
        { label: "Home", href: "#" },
        { label: "About", href: "#" },
        { label: "Events", href: "#" },
        { label: "Sponsors", href: "#" },
        { label: "Pricing", href: "#" }
      ]}
    />

    <SocialFlipButton
      platform="twitter"
      href="https://twitter.com"
    />
    </div>
    <LiquidText text="ROSHAN" color="#ddd21a" />
    <Bg></Bg>
    </>
  )
}

export default Temp
